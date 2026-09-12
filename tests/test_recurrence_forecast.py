import unittest
from datetime import date
from decimal import Decimal

from code.forecast import simulate_90_day_forecast
from code.models import FinancialEvent, FinancialProfile, NormalizedFinancialEvent
from code.event_normalizer import normalize_events


def reconciled(event_id, event_date, flexibility="fixed"):
    original = FinancialEvent(
        event_id, "user_test", "expense", "Test event", "other", "debit",
        Decimal("10.00"), "EUR", event_date, event_date, "settled", None,
        flexibility, None,
    )
    return NormalizedFinancialEvent(
        event_id, original, Decimal("10.00"), "EUR", event_date, event_date,
        "settled", "Test event", "csv", "csv", "csv", "csv", False, [], [],
    )


class TestRecurrenceForecast(unittest.TestCase):
    def test_monthly_occurrences_are_generated_inside_horizon(self):
        normalized = normalize_events(
            [
                reconciled("jan", date(2026, 1, 10)),
                reconciled("feb", date(2026, 2, 10)),
                reconciled("mar", date(2026, 3, 10)),
            ]
        )
        profile = FinancialProfile("user_test", "EUR", Decimal("100"), Decimal("0"), [], [], [], [], [], None)
        forecast = simulate_90_day_forecast(profile, normalized, date(2026, 4, 1))
        applied = {
            item.date: item.outflows
            for item in forecast.daily_balances
            if item.applied_event_ids
        }
        self.assertEqual(applied[date(2026, 4, 10)], Decimal("10.00"))
        self.assertEqual(applied[date(2026, 5, 10)], Decimal("10.00"))
        self.assertNotIn(date(2026, 7, 10), applied)

    def test_recurring_flexible_event_remains_eligible(self):
        item = normalize_events(
            [
                reconciled("a", date(2026, 1, 1), "reducible"),
                reconciled("b", date(2026, 2, 1), "reducible"),
                reconciled("c", date(2026, 3, 1), "reducible"),
            ]
        )["a"]
        self.assertEqual(item.flexibility, "reducible")
        self.assertTrue(item.recurrence_explicit)


if __name__ == "__main__":
    unittest.main()
