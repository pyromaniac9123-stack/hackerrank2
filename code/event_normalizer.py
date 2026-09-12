from collections import defaultdict
from datetime import date
from typing import Dict, Iterable, Mapping

from code.models import NormalizedEvent, NormalizedFinancialEvent


_DIRECTIONS = {"credit", "debit", "non_cash"}
_STATUS_CATEGORIES = {
    "settled": "confirmed_settled",
    "scheduled": "future_confirmed",
    "pending": "pending",
    "failed": "failed",
    "cancelled": "cancelled",
    "unrealized": "estimate",
    "forecast": "estimate",
    "estimated": "estimate",
}


def _status_category(status: str) -> str:
    return _STATUS_CATEGORIES.get(status.lower(), "other")


def _sort_date(value: date | None) -> date:
    return value or date.max


def _recurrence_key(original) -> tuple:
    return (
        original.user_id,
        original.event_type,
        original.description,
        original.category,
        original.direction.lower(),
        original.currency,
        original.flexibility,
        original.minimum_allowed_amount,
    )


def _monthly_pattern(group: list[NormalizedEvent]) -> bool:
    dates = sorted(
        item.settlement_date or item.event_date
        for item in group
        if item.settlement_date or item.event_date
    )
    if len(dates) < 3 or len({item.day for item in dates}) != 1:
        return False
    return all(
        (dates[index].year * 12 + dates[index].month)
        - (dates[index - 1].year * 12 + dates[index - 1].month)
        == 1
        for index in range(1, len(dates))
    )


def normalize_events(
    reconciled_events: (
        Iterable[NormalizedFinancialEvent]
        | Mapping[str, NormalizedFinancialEvent]
    ),
) -> Dict[str, NormalizedEvent]:
    values = (
        reconciled_events.values()
        if isinstance(reconciled_events, Mapping)
        else reconciled_events
    )
    normalized = []
    grouped = defaultdict(list)
    for reconciled in values:
        original = reconciled.original_event
        direction = original.direction.lower()
        if direction not in _DIRECTIONS:
            raise ValueError(
                f"Unsupported direction for event {original.event_id}: "
                f"{original.direction}"
            )
        event_date = reconciled.canonical_event_date
        settlement_date = reconciled.canonical_settlement_date
        item = NormalizedEvent(
                event_id=reconciled.event_id,
                user_id=original.user_id,
                event_type=original.event_type,
                category=original.category,
                description=reconciled.canonical_description,
                direction=direction,
                amount=reconciled.canonical_amount,
                currency=reconciled.canonical_currency,
                event_date=event_date,
                settlement_date=settlement_date,
                status=reconciled.canonical_status,
                status_category=_status_category(reconciled.canonical_status),
                flexibility=original.flexibility,
                minimum_allowed_amount=original.minimum_allowed_amount,
                linked_event_id=original.linked_event_id,
                recurrence_key=None,
                recurrence_rule=None,
                recurrence_explicit=False,
                reconciled_event=reconciled,
                sort_key=(
                    _sort_date(settlement_date),
                    _sort_date(event_date),
                    reconciled.event_id,
                ),
        )
        normalized.append(item)
        if (
            item.status_category in {"confirmed_settled", "future_confirmed"}
            and item.amount is not None
            and direction in {"credit", "debit"}
        ):
            grouped[_recurrence_key(original)].append(item)

    for group in grouped.values():
        recurring = _monthly_pattern(group) or (
            len(group) == 1 and group[0].event_type == "subscription"
        )
        if not recurring:
            continue
        anchor = max(
            group,
            key=lambda item: (_sort_date(item.settlement_date or item.event_date), item.event_id),
        )
        anchor_date = anchor.settlement_date or anchor.event_date
        if anchor_date is None:
            continue
        key = "|".join(str(value) for value in _recurrence_key(anchor.reconciled_event.original_event))
        rule = f"monthly_day:{anchor_date.day}"
        for item in group:
            item.recurrence_key = key
            item.recurrence_rule = rule
            item.recurrence_explicit = True

    normalized.sort(key=lambda item: item.sort_key)
    return {item.event_id: item for item in normalized}
