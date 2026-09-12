import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping

from code.models import (
    FinancialEvent,
    Message,
    NormalizedEvent,
    NormalizedFinancialEvent,
)


_AMOUNT_CURRENCY_PATTERN = re.compile(
    r"\b(?P<currency>INR|ZAR|IDR|USD|EUR)\s*"
    r"(?P<amount>[0-9][0-9,]*(?:\.[0-9]+)?)\b",
    re.IGNORECASE,
)
_DATE_PATTERN = re.compile(r"\b(?P<date>\d{4}-\d{2}-\d{2})\b")
_CANCELLED_PATTERN = re.compile(
    r"\b(cancelled|canceled|retracted|withdrawn|revoked)\b",
    re.IGNORECASE,
)
_CASH_FLOW_PATTERN = re.compile(
    r"\b(salary|pay|payout|payment|refund|income|receipt|credit)\b",
    re.IGNORECASE,
)
_EXPECTED_FLOW_PATTERN = re.compile(
    r"\b(will|resumes?|confirmed|expected|scheduled|due|first|approved|"
    r"starting|starts|begins|applies)\b",
    re.IGNORECASE,
)
def _parse_message_cash_flow(message: Message) -> tuple[Decimal, str, date, str] | None:
    text = message.message_text
    if message.related_event_id:
        return None
    if (
        _CANCELLED_PATTERN.search(text)
        or not _CASH_FLOW_PATTERN.search(text)
        or not _EXPECTED_FLOW_PATTERN.search(text)
    ):
        return None

    clauses = re.split(r"[.!?;]\s+|\n+", text)
    pairs = []
    for clause in clauses:
        amount_match = _AMOUNT_CURRENCY_PATTERN.search(clause)
        date_match = _DATE_PATTERN.search(clause)
        if amount_match and date_match:
            pairs.append((clause, amount_match, date_match))
    if not pairs:
        amounts = list(_AMOUNT_CURRENCY_PATTERN.finditer(text))
        dates = list(_DATE_PATTERN.finditer(text))
        if len(amounts) == 1 and len(dates) == 1:
            pairs.append((text, amounts[0], dates[0]))
    if len(pairs) != 1:
        return None
    clause, amount_match, date_match = pairs[0]
    if re.search(r"\b(hypothetical|if|might|could|possibly|pending|unrealized|"
                 r"estimate|forecast|history|historical)\b", clause, re.IGNORECASE):
        return None

    try:
        amount = Decimal(amount_match.group("amount").replace(",", ""))
        event_date = date.fromisoformat(date_match.group("date"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"Invalid amount or date in message {message.message_id}"
        ) from exc

    has_income_language = re.search(
        r"\b(salary|income|receipt|payout|credit|refund)\b", clause, re.IGNORECASE
    )
    direction = "credit" if has_income_language else "debit"
    return amount, amount_match.group("currency").upper(), event_date, direction


def message_cash_flows(
    messages: Iterable[Message] | Mapping[str, Message],
    normalized_events: Iterable[NormalizedEvent | NormalizedFinancialEvent],
) -> list[NormalizedFinancialEvent]:
    """Create only explicitly dated and quantified message cash flows."""
    message_values = messages.values() if isinstance(messages, Mapping) else messages
    events = list(normalized_events)
    result: list[NormalizedFinancialEvent] = []

    for message in message_values:
        parsed = _parse_message_cash_flow(message)
        if parsed is None:
            continue
        amount, currency, event_date, direction = parsed
        equivalent = False
        for event in events:
            if isinstance(event, NormalizedEvent):
                same_transaction = (
                    event.user_id == message.user_id
                    and event.amount == amount
                    and event.currency.upper() == currency
                    and event.direction.lower() == direction
                    and event.event_date == event_date
                )
            else:
                same_transaction = (
                    event.original_event.user_id == message.user_id
                    and event.canonical_amount == amount
                    and event.canonical_currency.upper() == currency
                    and event.original_event.direction.lower() == direction
                    and event.canonical_event_date == event_date
                )
            if same_transaction:
                equivalent = True
                break
        if equivalent:
            continue

        event_id = f"message_flow:{message.message_id}"
        original = FinancialEvent(
            event_id=event_id,
            user_id=message.user_id,
            event_type="income" if direction == "credit" else "expense",
            description=message.message_text,
            category="salary" if re.search(r"\bsalary\b", message.message_text, re.IGNORECASE) else "other",
            direction=direction,
            amount=amount,
            currency=currency,
            event_date=event_date,
            settlement_date=event_date,
            status="scheduled",
            linked_event_id=None,
            flexibility="fixed",
            minimum_allowed_amount=None,
        )
        result.append(
            NormalizedFinancialEvent(
                event_id=event_id,
                original_event=original,
                canonical_amount=amount,
                canonical_currency=currency,
                canonical_event_date=event_date,
                canonical_settlement_date=event_date,
                canonical_status="scheduled",
                canonical_description=message.message_text,
                amount_source=f"message:{message.message_id}",
                currency_source=f"message:{message.message_id}",
                status_source=f"message:{message.message_id}",
                description_source=f"message:{message.message_id}",
                recovered_from_evidence=True,
                evidence_sources=[f"message:{message.message_id}"],
                reconciliation_notes=["cash flow created from explicit message evidence"],
            )
        )
    return result
