import unittest
from copy import deepcopy
from datetime import date
from decimal import Decimal

from code.data_loader import load_financial_events, load_images, load_messages
from code.event_normalizer import normalize_events
from code.image_extractor import extract_all_images
from code.models import FinancialEvent, NormalizedFinancialEvent
from code.reconciliation import reconcile_events


def reconciled(
    event_id="event_test",
    amount=Decimal("10.00"),
    direction="debit",
    status="settled",
    event_date=date(2026, 1, 2),
    settlement_date=date(2026, 1, 4),
    linked_event_id=None,
    currency="EUR",
):
    original = FinancialEvent(
        event_id=event_id,
        user_id="user_test",
        event_type="expense",
        description="Test event",
        category="other",
        direction=direction,
        amount=amount,
        currency=currency,
        event_date=event_date,
        settlement_date=settlement_date,
        status=status,
        linked_event_id=linked_event_id,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    return NormalizedFinancialEvent(
        event_id=event_id,
        original_event=original,
        canonical_amount=amount,
        canonical_currency=currency,
        canonical_event_date=event_date,
        canonical_settlement_date=settlement_date,
        canonical_status=status,
        canonical_description="Test event",
        amount_source="csv",
        currency_source="csv",
        status_source="csv",
        description_source="csv",
        recovered_from_evidence=False,
        evidence_sources=[],
        reconciliation_notes=[],
    )


class TestEventNormalizer(unittest.TestCase):
    def test_confirmed_expense(self):
        item = normalize_events([reconciled()])["event_test"]
        self.assertEqual(item.direction, "debit")
        self.assertEqual(item.status_category, "confirmed_settled")
        self.assertEqual(item.amount, Decimal("10.00"))

    def test_confirmed_income(self):
        item = normalize_events([reconciled(direction="credit", event_id="income")])["income"]
        self.assertEqual(item.direction, "credit")

    def test_missing_amount_remains_none(self):
        item = normalize_events([reconciled(amount=None)])["event_test"]
        self.assertIsNone(item.amount)

    def test_image_recovered_amount_survives(self):
        source = reconciled(amount=Decimal("19.00"))
        source.amount_source = "image:image_test"
        source.recovered_from_evidence = True
        item = normalize_events([source])["event_test"]
        self.assertEqual(item.amount, Decimal("19.00"))
        self.assertEqual(item.reconciled_event.amount_source, "image:image_test")

    def test_currency_is_preserved_without_conversion(self):
        self.assertEqual(normalize_events([reconciled()])["event_test"].currency, "EUR")

    def test_event_and_settlement_dates_are_distinct(self):
        item = normalize_events([reconciled()])["event_test"]
        self.assertEqual(item.event_date, date(2026, 1, 2))
        self.assertEqual(item.settlement_date, date(2026, 1, 4))

    def test_pending_cancelled_failed_and_forecast_remain_present(self):
        statuses = ["pending", "cancelled", "failed", "forecast"]
        result = normalize_events(
            [reconciled(event_id=status, status=status) for status in statuses]
        )
        self.assertEqual(set(result), set(statuses))
        self.assertEqual(result["pending"].status_category, "pending")
        self.assertEqual(result["cancelled"].status_category, "cancelled")
        self.assertEqual(result["failed"].status_category, "failed")
        self.assertEqual(result["forecast"].status_category, "estimate")

    def test_linked_event_is_preserved(self):
        item = normalize_events([reconciled(linked_event_id="event_parent")])["event_test"]
        self.assertEqual(item.linked_event_id, "event_parent")

    def test_no_recurrence_is_invented(self):
        result = normalize_events(
            [reconciled(event_id="a"), reconciled(event_id="b", event_date=date(2026, 2, 2))]
        )
        self.assertTrue(all(item.recurrence_key is None for item in result.values()))
        self.assertTrue(all(not item.recurrence_explicit for item in result.values()))

    def test_repeated_monthly_events_get_recurrence_metadata(self):
        items = [
            reconciled(event_id=f"monthly_{month}", event_date=date(2026, month, 15), settlement_date=date(2026, month, 15))
            for month in (1, 2, 3)
        ]
        result = normalize_events(items)
        self.assertTrue(all(item.recurrence_explicit for item in result.values()))
        self.assertEqual(result["monthly_1"].recurrence_rule, "monthly_day:15")
        self.assertEqual(result["monthly_1"].recurrence_key, result["monthly_3"].recurrence_key)

    def test_direction_is_normalized_and_unknown_rejected(self):
        self.assertEqual(
            normalize_events([reconciled(direction="CREDIT")])["event_test"].direction,
            "credit",
        )
        with self.assertRaises(ValueError):
            normalize_events([reconciled(direction="unknown")])

    def test_ordering_is_deterministic_and_same_day_events_remain_separate(self):
        result = normalize_events(
            [
                reconciled(event_id="b", event_date=date(2026, 1, 1), settlement_date=date(2026, 1, 3)),
                reconciled(event_id="a", event_date=date(2026, 1, 1), settlement_date=date(2026, 1, 3)),
            ]
        )
        self.assertEqual(list(result), ["a", "b"])
        self.assertEqual(len(result), 2)

    def test_original_reconciled_objects_are_not_mutated(self):
        source = reconciled()
        before = deepcopy(source)
        normalize_events([source])
        self.assertEqual(source, before)

    def test_all_real_events_normalize(self):
        root = __import__("pathlib").Path("dataset")
        events = load_financial_events(root / "financial_events.csv")
        records = load_images(root / "images.csv", root / "media/images")
        extractions = extract_all_images(records)
        reconciled_events = reconcile_events(events, load_messages(root / "messages.csv"), records, extractions)
        result = normalize_events(reconciled_events)
        self.assertEqual(len(result), len(events))
        self.assertEqual(result["event_01"].status_category, "confirmed_settled")


if __name__ == "__main__":
    unittest.main()
