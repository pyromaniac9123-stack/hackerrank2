from dataclasses import replace
import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Mapping

from code.models import DailyBalance, FinancialProfile, ForecastResult, NormalizedEvent


_APPLICABLE_STATUS_CATEGORIES = {"confirmed_settled", "future_confirmed", "pending"}
_NON_APPLICABLE_STATUS_CATEGORIES = {
    "pending",
    "failed",
    "cancelled",
    "estimate",
}


def _event_date(event: NormalizedEvent) -> date | None:
    # Pending debits reserve cash; pending credits are deliberately ignored.
    if event.status_category in _APPLICABLE_STATUS_CATEGORIES and not (
        event.status_category == "pending" and event.direction == "credit"
    ):
        return event.settlement_date or event.event_date
    return None


def _next_month(value: date) -> date:
    year = value.year + (value.month == 12)
    month = 1 if value.month == 12 else value.month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _recurring_occurrences(
    events: list[NormalizedEvent], start_date: date, end_date: date
) -> list[NormalizedEvent]:
    groups: dict[str, list[NormalizedEvent]] = {}
    for event in events:
        if event.recurrence_explicit and event.recurrence_key:
            groups.setdefault(event.recurrence_key, []).append(event)

    occurrences: list[NormalizedEvent] = []
    recurring_ids = set()
    for group in groups.values():
        template = max(
            group,
            key=lambda item: (_event_date(item) or date.min, item.event_id),
        )
        anchor = _event_date(template)
        if anchor is None:
            continue
        current = anchor
        represented = {
            (_event_date(item), item.direction, item.amount)
            for item in group
        }
        while current <= end_date:
            if current >= start_date:
                settlement = current
                if template.event_date and template.settlement_date:
                    settlement = current + (
                        template.settlement_date - template.event_date
                    )
                identity = (current, template.direction, template.amount)
                if identity not in represented:
                    occurrences.append(
                        replace(
                            template,
                            event_id=f"{template.event_id}@{current.isoformat()}",
                            event_date=current,
                            settlement_date=settlement,
                            recurrence_source_event_id=template.event_id,
                            occurrence_date=current,
                        )
                    )
            current = _next_month(current)

    return occurrences, recurring_ids


def simulate_90_day_forecast(
    profile: FinancialProfile,
    events: Iterable[NormalizedEvent] | Mapping[str, NormalizedEvent],
    request_date: date,
) -> ForecastResult:
    """Simulate daily balances for exactly 90 calendar days.

    Confirmed events are applied on settlement_date when present, otherwise
    event_date. Same-day movements are processed by event_id for stable,
    reproducible ordering; the daily totals are independent of that order.
    """
    event_values = list(events.values() if isinstance(events, Mapping) else events)
    start_date = request_date
    end_date = request_date + timedelta(days=89)
    movements: dict[date, list[NormalizedEvent]] = {}
    skipped_event_ids: list[str] = []

    recurring_occurrences, recurring_ids = _recurring_occurrences(
        event_values, start_date, end_date
    )
    forecast_events = event_values + recurring_occurrences

    for event in forecast_events:
        movement_date = _event_date(event)
        if movement_date is None:
            if event.status_category not in _NON_APPLICABLE_STATUS_CATEGORIES:
                skipped_event_ids.append(event.event_id)
            continue
        if not start_date <= movement_date <= end_date:
            continue
        if event.amount is None:
            skipped_event_ids.append(event.event_id)
            continue
        if event.direction == "non_cash":
            skipped_event_ids.append(event.event_id)
            continue
        if event.direction not in {"credit", "debit"}:
            raise ValueError(
                f"Unsupported normalized direction for event {event.event_id}: "
                f"{event.direction}"
            )
        movements.setdefault(movement_date, []).append(event)

    for same_day_events in movements.values():
        same_day_events.sort(key=lambda event: event.event_id)

    daily_balances: list[DailyBalance] = []
    balance = profile.current_available_balance
    current_date = start_date
    while current_date <= end_date:
        opening_balance = balance
        inflows = Decimal("0")
        outflows = Decimal("0")
        applied_event_ids: list[str] = []
        for event in movements.get(current_date, []):
            amount = event.amount
            if event.direction == "credit":
                inflows += amount
                balance += amount
            else:
                outflows += amount
                balance -= amount
            applied_event_ids.append(event.event_id)
        daily_balances.append(
            DailyBalance(
                date=current_date,
                opening_balance=opening_balance,
                inflows=inflows,
                outflows=outflows,
                closing_balance=balance,
                applied_event_ids=applied_event_ids,
            )
        )
        current_date += timedelta(days=1)

    minimum_day = min(
        daily_balances,
        key=lambda daily: (daily.closing_balance, daily.date),
    )
    return ForecastResult(
        request_date=request_date,
        end_date=end_date,
        minimum_balance_required=profile.minimum_balance_to_keep,
        daily_balances=daily_balances,
        minimum_projected_balance=minimum_day.closing_balance,
        minimum_balance_date=minimum_day.date,
        skipped_event_ids=sorted(set(skipped_event_ids)),
    )
