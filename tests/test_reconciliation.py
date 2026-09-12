import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from code.data_loader import (
    load_financial_events,
    load_images,
    load_messages,
)
from code.image_extractor import extract_all_images
from code.models import FinancialEvent, ImageExtraction, ImageRecord, Message
from code.reconciliation import reconcile_events


def event(
    event_id="event_test",
    amount=None,
    status="forecast",
    direction="debit",
    currency="INR",
):
    return FinancialEvent(
        event_id=event_id,
        user_id="user_test",
        event_type="expense",
        description="Test event",
        category="other",
        direction=direction,
        amount=amount,
        currency=currency,
        event_date=date(2026, 1, 1),
        settlement_date=date(2026, 1, 2),
        status=status,
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )


def message(text, message_id="message_test", source_type="bank", sent_at="2026-01-03T10:00:00+00:00"):
    return Message(
        message_id=message_id,
        user_id="user_test",
        request_id=None,
        related_event_id="event_test",
        sent_at=datetime.fromisoformat(sent_at),
        source_type=source_type,
        message_text=text,
    )


class TestReconciliation(unittest.TestCase):
    def test_complete_csv_event_remains_unchanged(self):
        original = event(amount=Decimal("10.00"), status="settled")
        result = reconcile_events({original.event_id: original})[original.event_id]
        self.assertEqual(result.canonical_amount, Decimal("10.00"))
        self.assertEqual(result.canonical_status, "settled")
        self.assertEqual(result.amount_source, "csv")
        self.assertIs(result.original_event, original)

    def test_blank_amount_is_recovered_from_explicit_image_link(self):
        original = event(amount=None)
        record = ImageRecord("image_test", "user_test", None, original.event_id, "image_test.png", Path("image_test.png"))
        extraction = ImageExtraction(
            "image_test", "image_test.png", "Total INR 19.00", "receipt",
            Decimal("19.00"), "INR", date(2026, 1, 2), "Test", None, Decimal("0.9")
        )
        result = reconcile_events(
            {original.event_id: original}, image_records=[record], image_extractions=[extraction]
        )[original.event_id]
        self.assertEqual(result.canonical_amount, Decimal("19.00"))
        self.assertEqual(result.amount_source, "image:image_test")

    def test_blank_amount_without_evidence_is_none(self):
        result = reconcile_events({"event_test": event(amount=None)})["event_test"]
        self.assertIsNone(result.canonical_amount)

    def test_image_reconciliation_does_not_modify_original_event(self):
        original = event(amount=None)
        record = ImageRecord("image_test", "user_test", None, original.event_id, "image_test.png", None)
        extraction = ImageExtraction("image_test", "image_test.png", "19", None, Decimal("19"), "INR", None, None, None, None)
        reconcile_events({"event_test": original}, [])[original.event_id]
        reconcile_events({"event_test": original}, image_records=[record], image_extractions=[extraction])
        self.assertIsNone(original.amount)

    def test_explicit_cancellation_overrides_forecast(self):
        result = reconcile_events({"event_test": event()}, [message("The event is cancelled.")])["event_test"]
        self.assertEqual(result.canonical_status, "cancelled")

    def test_explicit_settlement_overrides_estimate(self):
        result = reconcile_events({"event_test": event()}, [message("Payment completed and settled.")])["event_test"]
        self.assertEqual(result.canonical_status, "settled")

    def test_explicit_amendment_overrides_old_value(self):
        original = event(amount=Decimal("10.00"), status="forecast")
        result = reconcile_events(
            {"event_test": original},
            [message("The amount was amended to 25.00.", sent_at="2026-01-04T10:00:00+00:00")],
        )["event_test"]
        self.assertEqual(result.canonical_amount, Decimal("25.00"))
        self.assertEqual(result.amount_source, "message:message_test")

    def test_newer_same_source_evidence_wins(self):
        result = reconcile_events(
            {"event_test": event(amount=None)},
            [
                message("estimated amount 10.00", message_id="old", sent_at="2026-01-02T10:00:00+00:00"),
                message("estimated amount 20.00", message_id="new", sent_at="2026-01-03T10:00:00+00:00"),
            ],
        )["event_test"]
        self.assertEqual(result.canonical_amount, Decimal("20.00"))
        self.assertEqual(result.amount_source, "message:new")

    def test_settled_evidence_beats_estimate(self):
        result = reconcile_events(
            {"event_test": event(amount=None)},
            [
                message("estimated amount 20.00", message_id="estimate"),
                message("settled amount 10.00", message_id="settled", sent_at="2026-01-02T10:00:00+00:00"),
            ],
        )["event_test"]
        self.assertEqual(result.canonical_amount, Decimal("10.00"))

    def test_ambiguous_debit_amount_uses_safer_higher_value(self):
        result = reconcile_events(
            {"event_test": event(amount=None)},
            [
                message("amount 10.00", message_id="a", sent_at="2026-01-02T10:00:00+00:00"),
                message("amount 20.00", message_id="b", sent_at="2026-01-02T10:00:00+00:00"),
            ],
        )["event_test"]
        self.assertEqual(result.canonical_amount, Decimal("20.00"))
        self.assertIn("ambiguous amount", " ".join(result.reconciliation_notes))

    def test_conflict_has_traceable_provenance(self):
        result = reconcile_events(
            {"event_test": event(amount=None)},
            [message("amount 10.00", message_id="a"), message("amount 20.00", message_id="b")],
        )["event_test"]
        self.assertEqual(set(result.evidence_sources), {"message:a", "message:b"})

    def test_unrelated_messages_and_images_are_not_attached(self):
        unrelated = Message("m", "user_test", None, None, datetime.now(timezone.utc), "bank", "settled amount 9.00")
        record = ImageRecord("image_test", "user_test", None, None, "image_test.png", None)
        extraction = ImageExtraction("image_test", "image_test.png", "Total 9.00", None, Decimal("9"), "INR", None, None, None, None)
        result = reconcile_events({"event_test": event(amount=None)}, [unrelated], [record], [extraction])["event_test"]
        self.assertIsNone(result.canonical_amount)
        self.assertEqual(result.evidence_sources, [])

    def test_currency_is_preserved_without_conversion(self):
        original = event(amount=Decimal("5"), currency="USD")
        result = reconcile_events({"event_test": original})["event_test"]
        self.assertEqual(result.canonical_currency, "USD")

    def test_real_dataset_reconciles_and_recovers_blank_amounts(self):
        root = Path("dataset")
        events = load_financial_events(root / "financial_events.csv")
        records = load_images(root / "images.csv", root / "media/images")
        extractions = extract_all_images(records.values())
        result = reconcile_events(events, load_messages(root / "messages.csv"), records.values(), extractions.values())
        self.assertEqual(len(result), len(events))
        linked_ids = {record.related_event_id for record in records.values()}
        self.assertEqual(
            sum(result[event_id].amount_source != "csv" for event_id in linked_ids),
            16,
        )
        self.assertTrue(
            all(
                result[event_id].original_event.amount is None
                for event_id in linked_ids
            )
        )


if __name__ == "__main__":
    unittest.main()
