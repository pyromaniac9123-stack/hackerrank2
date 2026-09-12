import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Iterable, Mapping, Optional

from code.models import (
    FinancialEvent,
    ImageExtraction,
    ImageRecord,
    Message,
    NormalizedFinancialEvent,
)


@dataclass(frozen=True)
class _Evidence:
    source_id: str
    source_kind: str
    source_group: str
    observed_at: datetime
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    explicit_action: bool = False
    settled_fact: bool = False
    estimate: bool = False


_STATUS_PATTERNS = (
    ("cancelled", re.compile(r"\b(cancelled|canceled)\b", re.IGNORECASE)),
    ("settled", re.compile(r"\b(settled|completed|paid)\b", re.IGNORECASE)),
    ("amended", re.compile(r"\b(amended|revised|updated|replaced)\b", re.IGNORECASE)),
)
_AMOUNT_PATTERN = re.compile(
    r"(?:amount|total|payable|salary|payment|value)[^\d-]*"
    r"([0-9][0-9,]*(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
_CURRENCY_PATTERN = re.compile(r"\b(INR|ZAR|IDR|USD|EUR)\b", re.IGNORECASE)


def _message_evidence(message: Message) -> Optional[_Evidence]:
    if not message.related_event_id:
        return None
    status = None
    explicit_action = False
    for candidate, pattern in _STATUS_PATTERNS:
        if pattern.search(message.message_text):
            status = candidate
            explicit_action = candidate in {"cancelled", "settled", "amended"}
            break
    amount_match = _AMOUNT_PATTERN.search(message.message_text)
    amount = (
        Decimal(amount_match.group(1).replace(",", ""))
        if amount_match
        else None
    )
    currency_match = _CURRENCY_PATTERN.search(message.message_text)
    estimate = bool(re.search(r"\b(estimate|estimated|forecast|expected)\b", message.message_text, re.IGNORECASE))
    return _Evidence(
        source_id=f"message:{message.message_id}",
        source_kind="message",
        source_group=message.source_type,
        observed_at=message.sent_at,
        amount=amount,
        currency=currency_match.group(1).upper() if currency_match else None,
        status=status,
        description=message.message_text,
        explicit_action=explicit_action,
        settled_fact=status == "settled",
        estimate=estimate,
    )


def _image_evidence(
    image_records: Iterable[ImageRecord],
    image_extractions: Iterable[ImageExtraction],
) -> list[tuple[str, _Evidence]]:
    records = {record.image_id: record for record in image_records}
    result: list[tuple[str, _Evidence]] = []
    for extraction in image_extractions:
        record = records.get(extraction.source_image_id)
        linked_event_id = record.related_event_id if record else None
        if not linked_event_id:
            continue
        observed = extraction.extracted_date or date.min
        result.append(
            (
                linked_event_id,
                _Evidence(
                    source_id=f"image:{extraction.source_image_id}",
                    source_kind="image",
                    source_group=extraction.source_image_id,
                    observed_at=datetime.combine(observed, datetime.min.time()),
                    amount=extraction.extracted_amount,
                    currency=extraction.extracted_currency,
                    description=extraction.extracted_description,
                ),
            )
        )
    return result


def _choose_evidence(
    event: FinancialEvent,
    candidates: list[_Evidence],
    field: str,
) -> tuple[Optional[object], str, list[str]]:
    usable = [candidate for candidate in candidates if getattr(candidate, field) is not None]
    if not usable:
        return None, "unknown", []

    def rank(candidate: _Evidence) -> tuple[int, int, datetime]:
        explicit = int(candidate.explicit_action)
        settled = int(candidate.settled_fact)
        not_estimate = int(not candidate.estimate)
        observed_at = candidate.observed_at
        if observed_at.tzinfo is not None:
            observed_at = observed_at.astimezone().replace(tzinfo=None)
        return explicit, settled + not_estimate, observed_at

    strongest = max(usable, key=rank)
    same_rank = [candidate for candidate in usable if rank(candidate) == rank(strongest)]
    if field == "amount" and len({getattr(item, field) for item in same_rank}) > 1:
        values = [getattr(item, field) for item in same_rank]
        chosen = max(values) if event.direction == "debit" else min(values)
        return chosen, "ambiguous-safe-choice", [item.source_id for item in same_rank]
    return getattr(strongest, field), strongest.source_id, [item.source_id for item in usable]


def reconcile_events(
    events: Mapping[str, FinancialEvent],
    messages: Iterable[Message] | Mapping[str, Message] = (),
    image_records: Iterable[ImageRecord] | Mapping[str, ImageRecord] = (),
    image_extractions: Iterable[ImageExtraction] | Mapping[str, ImageExtraction] = (),
) -> Dict[str, NormalizedFinancialEvent]:
    message_values = messages.values() if isinstance(messages, Mapping) else messages
    record_values = (
        image_records.values()
        if isinstance(image_records, Mapping)
        else image_records
    )
    extraction_values = (
        image_extractions.values()
        if isinstance(image_extractions, Mapping)
        else image_extractions
    )
    evidence_by_event: dict[str, list[_Evidence]] = {event_id: [] for event_id in events}
    for message in message_values:
        evidence = _message_evidence(message)
        if evidence and message.related_event_id in evidence_by_event:
            evidence_by_event[message.related_event_id].append(evidence)
    for event_id, evidence in _image_evidence(record_values, extraction_values):
        if event_id in evidence_by_event:
            evidence_by_event[event_id].append(evidence)

    normalized: Dict[str, NormalizedFinancialEvent] = {}
    for event_id, event in events.items():
        candidates = evidence_by_event[event_id]
        sources = [candidate.source_id for candidate in candidates]
        notes: list[str] = []

        amount = event.amount
        amount_source = "csv"
        if amount is None:
            recovered, amount_source, _ = _choose_evidence(event, candidates, "amount")
            amount = recovered
            if amount is not None:
                notes.append("amount recovered from linked evidence")
        elif any(candidate.explicit_action and candidate.amount is not None for candidate in candidates):
            recovered, source, _ = _choose_evidence(event, candidates, "amount")
            if recovered is not None:
                amount, amount_source = recovered, source
                notes.append("amount amended by explicit evidence")

        currency = event.currency
        currency_source = "csv"
        if not currency:
            recovered, currency_source, _ = _choose_evidence(event, candidates, "currency")
            currency = recovered or ""
        status = event.status
        status_source = "csv"
        status_candidates = [candidate for candidate in candidates if candidate.status]
        if status_candidates:
            explicit = [candidate for candidate in status_candidates if candidate.explicit_action]
            settled = [candidate for candidate in status_candidates if candidate.settled_fact]
            eligible = explicit or settled or status_candidates
            chosen = max(eligible, key=lambda candidate: candidate.observed_at)
            if (
                chosen.explicit_action
                or (status not in {"settled", "cancelled"} and chosen.settled_fact)
            ):
                status, status_source = chosen.status or status, chosen.source_id
                notes.append("status selected by evidence precedence")

        description = event.description
        description_source = "csv"
        if not description:
            recovered, description_source, _ = _choose_evidence(event, candidates, "description")
            description = recovered or ""

        if amount_source == "ambiguous-safe-choice":
            notes.append("ambiguous amount resolved conservatively")
        normalized[event_id] = NormalizedFinancialEvent(
            event_id=event_id,
            original_event=event,
            canonical_amount=amount,
            canonical_currency=currency,
            canonical_event_date=event.event_date,
            canonical_settlement_date=event.settlement_date,
            canonical_status=status,
            canonical_description=description,
            amount_source=amount_source,
            currency_source=currency_source,
            status_source=status_source,
            description_source=description_source,
            recovered_from_evidence=any(source != "csv" for source in (amount_source, currency_source, status_source, description_source)),
            evidence_sources=sources,
            reconciliation_notes=notes,
        )
    return normalized
