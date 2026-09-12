import csv
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from code.data_loader import (
    load_exchange_rates,
    load_financial_events,
    load_financial_profiles,
    load_images,
    load_messages,
    load_payment_options,
    load_requests,
)
from code.decision import decide
from code.event_normalizer import normalize_events
from code.forecast import simulate_90_day_forecast
from code.image_extractor import extract_all_images
from code.message_cashflows import message_cash_flows
from code.models import FinalDecision, Request, NormalizedEvent
from code.utils import convert_amount
from code.planner import generate_payment_plans
from code.reconciliation import reconcile_events
from code.safety import evaluate_safety

OUTPUT_FIELDS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]


def _format_decision(request: Request, decision: FinalDecision) -> dict[str, str]:
    if decision.amount_safe_to_pay < 0 or (
        request.requested_amount is not None
        and decision.amount_safe_to_pay > request.requested_amount
    ):
        raise ValueError(f"Invalid amount_safe_to_pay for request {request.request_id}")
    return {
        "request_id": request.request_id,
        "amount_safe_to_pay": format(decision.amount_safe_to_pay, "f"),
        "affordability_status": decision.affordability_status,
        "recommended_payment_method": decision.recommended_payment_method,
        "payment_plan": decision.payment_plan,
        "earliest_date_for_full_payment": decision.earliest_date_for_full_payment,
        "spending_changes_needed": decision.spending_changes_needed,
        "decision_explanation": decision.decision_explanation,
    }


def generate_decisions(dataset_root: Path) -> list[tuple[Request, FinalDecision]]:
    requests = load_requests(dataset_root / "requests.csv")
    profiles = load_financial_profiles(dataset_root / "financial_profiles.csv")
    events = load_financial_events(dataset_root / "financial_events.csv")
    exchange_rates = load_exchange_rates(dataset_root / "exchange_rates.csv")
    payment_options = load_payment_options(dataset_root / "request_payment_options.csv")
    messages = load_messages(dataset_root / "messages.csv")
    images = load_images(dataset_root / "images.csv", dataset_root / "media" / "images")
    extractions = extract_all_images(images)
    reconciled = reconcile_events(events, messages, images, extractions)
    normalized_existing = normalize_events(reconciled)
    message_events = message_cash_flows(messages, normalized_existing.values())
    normalized = normalize_events(
        list(reconciled.values()) + message_events
    )
    # All forecast arithmetic is performed in the account's home currency.
    converted: dict[str, NormalizedEvent] = {}
    for event in normalized.values():
        profile = profiles.get(event.user_id)
        amount = event.amount
        currency = event.currency
        if profile and amount is not None and currency.upper() != profile.home_currency.upper():
            conversion_date = event.settlement_date or event.event_date
            if conversion_date is not None:
                amount = convert_amount(
                    amount, currency, profile.home_currency, conversion_date, exchange_rates
                )
                event = replace(event, amount=amount, currency=profile.home_currency)
        converted[event.event_id] = event
    normalized = converted
    events_by_user = {
        user_id: [event for event in normalized.values() if event.user_id == user_id]
        for user_id in profiles
    }
    results = []
    for request in requests.values():
        try:
            profile = profiles[request.user_id]
            user_events = events_by_user.get(request.user_id, [])
            forecast = simulate_90_day_forecast(profile, user_events, request.request_date)
            safety = evaluate_safety(request, profile, forecast)
            planner = generate_payment_plans(
                request, profile, user_events, forecast, safety, payment_options
            )
            results.append((request, decide(request, safety, planner)))
        except (KeyError, ValueError, FileNotFoundError) as exc:
            raise RuntimeError(
                f"Decision pipeline failed for request {request.request_id}: {exc}"
            ) from exc
    return results


def write_output(
    decisions: Iterable[tuple[Request, FinalDecision]], output_path: Path
) -> None:
    rows = [_format_decision(request, decision) for request, decision in decisions]
    request_ids = [row["request_id"] for row in rows]
    if len(request_ids) != len(set(request_ids)):
        raise ValueError("Cannot write output with duplicate request IDs")
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def run(dataset_root: Path, output_path: Path) -> list[tuple[Request, FinalDecision]]:
    decisions = generate_decisions(dataset_root)
    write_output(decisions, output_path)
    return decisions


if __name__ == "__main__":
    repository_root = Path(__file__).resolve().parent.parent
    run(repository_root / "dataset", repository_root / "output.csv")