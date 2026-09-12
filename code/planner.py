from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations
from typing import Iterable, Mapping, Optional

from code.models import (
    FinancialProfile,
    ForecastResult,
    NormalizedEvent,
    PaymentInstallment,
    PaymentOption,
    PaymentPlan,
    PlannerResult,
    Request,
    SafetyResult,
)


def _values(value):
    return value.values() if isinstance(value, Mapping) else value


def _profile_accepts(profile: FinancialProfile, method: str) -> bool:
    return method in profile.payment_methods_user_will_consider


def _payments_are_feasible(
    forecast: ForecastResult,
    installments: list[PaymentInstallment],
) -> tuple[bool, str]:
    payments = {}
    for installment in installments:
        payments[installment.payment_date] = (
            payments.get(installment.payment_date, Decimal("0"))
            + installment.amount
        )
    cumulative_payment = Decimal("0")
    for daily in forecast.daily_balances:
        cumulative_payment += payments.get(daily.date, Decimal("0"))
        if daily.closing_balance - cumulative_payment < forecast.minimum_balance_required:
            return False, f"minimum balance violated on {daily.date}"
    return True, "minimum balance preserved"


def _make_plan(
    installments: list[PaymentInstallment],
    method: str,
    option_id: Optional[str],
    changes: list[str],
    requested_amount: Decimal,
    forecast: ForecastResult,
    expected_total: Optional[Decimal] = None,
) -> PaymentPlan:
    total = sum((item.amount for item in installments), Decimal("0"))
    feasible, reason = _payments_are_feasible(forecast, installments)
    payable = requested_amount if expected_total is None else expected_total
    if total != payable:
        feasible = False
        reason = "installments do not exactly equal requested amount"
    return PaymentPlan(
        installments=installments,
        payment_method=method,
        payment_option_id=option_id,
        spending_changes=list(changes),
        total_amount=total,
        completion_date=max(item.payment_date for item in installments),
        feasible=feasible,
        feasibility_reason=reason,
    )


def _eligible_changes(
    request: Request,
    profile: FinancialProfile,
    events: list[NormalizedEvent],
) -> list[tuple[str, NormalizedEvent, Decimal]]:
    eligible = []
    allowed_categories = set(
        profile.expense_categories_user_is_willing_to_stop
        + profile.expense_categories_user_is_willing_to_reduce
    )
    for event in events:
        if (
            event.event_date is not None
            and event.event_date >= request.request_date
            and event.direction == "debit"
            and event.amount is not None
            and event.recurrence_explicit
            and event.flexibility in {"stoppable", "reducible", "reducible_or_stoppable"}
            and event.category in allowed_categories
            and event.status_category in {"confirmed_settled", "future_confirmed"}
        ):
            eligible.append((event.event_id, event, event.amount))
    return eligible


def _with_change_effect(
    forecast: ForecastResult,
    event_id: str,
    original_amount: Decimal,
    replacement: Decimal,
) -> ForecastResult:
    daily_balances = []
    event_by_day = {
        daily.date: set(daily.applied_event_ids) for daily in forecast.daily_balances
    }
    for daily in forecast.daily_balances:
        matching_ids = [
            applied_id for applied_id in event_by_day[daily.date]
            if applied_id == event_id or applied_id.startswith(f"{event_id}@")
        ]
        if not matching_ids:
            daily_balances.append(daily)
            continue
        reduction = sum(
            (original_amount - replacement for _ in matching_ids),
            Decimal("0"),
        )
        outflows = daily.outflows - reduction
        closing = daily.closing_balance + reduction
        daily_balances.append(
            type(daily)(
                date=daily.date,
                opening_balance=daily.opening_balance,
                inflows=daily.inflows,
                outflows=outflows,
                closing_balance=closing,
                applied_event_ids=list(daily.applied_event_ids),
            )
        )
    # Recompute subsequent openings/closings because reducing one recurring
    # occurrence changes the balance carried into every later day.
    carried = None
    rebuilt = []
    for daily in daily_balances:
        opening = daily.opening_balance if carried is None else carried
        closing = opening + daily.inflows - daily.outflows
        rebuilt.append(type(daily)(
            date=daily.date, opening_balance=opening, inflows=daily.inflows,
            outflows=daily.outflows, closing_balance=closing,
            applied_event_ids=list(daily.applied_event_ids),
        ))
        carried = closing
    daily_balances = rebuilt
    minimum_day = min(daily_balances, key=lambda item: (item.closing_balance, item.date))
    return type(forecast)(
        request_date=forecast.request_date,
        end_date=forecast.end_date,
        minimum_balance_required=forecast.minimum_balance_required,
        daily_balances=daily_balances,
        minimum_projected_balance=minimum_day.closing_balance,
        minimum_balance_date=minimum_day.date,
        skipped_event_ids=list(forecast.skipped_event_ids),
    )


def _rank(plan: PaymentPlan, request: Request) -> tuple:
    deadline_met = (
        request.desired_completion_date is None
        or plan.completion_date <= request.desired_completion_date
    )
    return (
        not deadline_met,
        bool(plan.spending_changes),
        plan.total_amount,
        plan.installments[0].payment_date,
        len(plan.installments),
        plan.payment_option_id or "",
    )


def generate_payment_plans(
    request: Request,
    profile: FinancialProfile,
    events: Iterable[NormalizedEvent] | Mapping[str, NormalizedEvent],
    forecast: ForecastResult,
    safety: SafetyResult,
    payment_options: Iterable[PaymentOption] | Mapping[str, PaymentOption] = (),
) -> PlannerResult:
    if request.requested_amount is None or request.requested_amount < Decimal("0"):
        raise ValueError(f"Request {request.request_id} has an invalid amount")
    requested = request.requested_amount
    normalized_events = list(_values(events))
    candidates: list[PaymentPlan] = []
    start = request.request_date

    if _profile_accepts(profile, "full_payment"):
        candidates.append(
            _make_plan(
                [PaymentInstallment(start, requested)],
                "full_payment",
                None,
                [],
                requested,
                forecast,
            )
        )

    earliest_full = None
    for daily in forecast.daily_balances:
        if daily.date < start:
            continue
        plan = _make_plan(
            [PaymentInstallment(daily.date, requested)],
            "full_payment",
            None,
            [],
            requested,
            forecast,
        )
        if plan.feasible:
            earliest_full = daily.date
            if daily.date != start and _profile_accepts(profile, "full_payment"):
                candidates.append(plan)
            break

    safe = safety.amount_safe_to_pay
    partial_date = None
    if Decimal("0") < safe < requested:
        remainder = requested - safe
        for daily in forecast.daily_balances:
            if daily.date <= start:
                continue
            candidate = [
                PaymentInstallment(start, safe),
                PaymentInstallment(daily.date, remainder),
            ]
            feasible, _ = _payments_are_feasible(forecast, candidate)
            if feasible:
                partial_date = daily.date
                break
    if (
        request.allows_partial_payment
        and _profile_accepts(profile, "partial_payment")
        and Decimal("0") < safe < requested
        and partial_date is not None
        and (
            request.desired_completion_date is None
            or partial_date <= request.desired_completion_date
        )
    ):
        candidates.append(
            _make_plan(
                [
                    PaymentInstallment(start, safe),
                    PaymentInstallment(partial_date, requested - safe),
                ],
                "partial_payment",
                None,
                [],
                requested,
                forecast,
            )
        )

    for option in _values(payment_options):
        if option.payment_method not in {"installments", "full_payment"}:
            continue
        if not _profile_accepts(profile, option.payment_method):
            continue
        if option.request_id != request.request_id:
            continue
        if (
            option.number_of_payments is None
            or option.payment_amount is None
            or option.first_payment_date is None
        ):
            continue
        if (
            profile.max_installment_months is not None
            and option.number_of_payments > 1
            and option.payment_frequency_days is not None
            and option.payment_frequency_days * (option.number_of_payments - 1)
            > profile.max_installment_months * 31
        ):
            continue
        payable = option.total_payable_amount
        if payable is None:
            payable = option.payment_amount * option.number_of_payments
        # A fee is part of the cash obligation.  Reject malformed offers
        # rather than silently changing their supplied schedule.
        if option.financing_fee is not None:
            expected = request.requested_amount + option.financing_fee
            if payable != expected:
                continue
        installments = [
            PaymentInstallment(
                option.first_payment_date
                + timedelta(days=(option.payment_frequency_days or 0) * index),
                option.payment_amount,
            )
            for index in range(option.number_of_payments)
        ]
        if any(
            installment.payment_date < forecast.request_date
            or installment.payment_date > forecast.end_date
            for installment in installments
        ):
            continue
        candidates.append(
            _make_plan(
                installments,
                option.payment_method,
                option.payment_option_id,
                [],
                requested,
                forecast,
                payable,
            )
        )

    eligible = _eligible_changes(request, profile, normalized_events)
    change_options = []
    for event_id, event, amount in eligible:
        if (
            event.flexibility in {"stoppable", "reducible_or_stoppable"}
            and event.category in profile.expense_categories_user_is_willing_to_stop
        ):
            change_options.append((event_id, Decimal("0"), f"stop:{event_id}"))
        if (
            event.flexibility in {"reducible", "reducible_or_stoppable"}
            and event.category in profile.expense_categories_user_is_willing_to_reduce
            and event.minimum_allowed_amount is not None
            and event.minimum_allowed_amount < amount
        ):
            change_options.append(
                (
                    event_id,
                    event.minimum_allowed_amount,
                    f"reduce_to:{event_id}:{event.minimum_allowed_amount}",
                )
            )
    for count in range(1, min(3, len(change_options)) + 1):
        for selected in combinations(change_options, count):
            if len({event_id for event_id, _, _ in selected}) != count:
                continue
            changes = [change for _, _, change in selected]
            changed_forecast = forecast
            for event_id, replacement, _ in selected:
                changed_forecast = _with_change_effect(
                    changed_forecast, event_id, amount, replacement
                )
            plan = _make_plan(
                [PaymentInstallment(start, requested)],
                "full_payment",
                None,
                changes,
                requested,
                changed_forecast,
            )
            candidates.append(plan)

    candidates.sort(key=lambda plan: _rank(plan, request))
    feasible = [
        plan for plan in candidates
        if plan.feasible
        and (
            request.desired_completion_date is None
            or plan.completion_date <= request.desired_completion_date
        )
        and plan.completion_date <= forecast.end_date
    ]
    return PlannerResult(candidates, feasible, earliest_full)
