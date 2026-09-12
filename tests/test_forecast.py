import unittest
from datetime import date, timedelta
from decimal import Decimal

from code.forecast import simulate_90_day_forecast
from code.models import FinancialProfile, NormalizedEvent


def profile(balance=Decimal("100.00"), minimum=Decimal("25.00")):
    return FinancialProfile(
        user_id="user_test",
        home_currency="USD",
        current_available_balance=balance,
        minimum_balance_to_keep=minimum,
        financial_priorities=[],
        expense_categories_to_protect=[],
        expense_categories_user_is_willing_to_reduce=[],
        expense_categories_user_is_willing_to_stop=[],
        payment_methods_user_will_consider=[],
        max_installment_months=None,
    )


def event(
    event_id,
    amount=Decimal("10.00"),
    direction="debit",
    status_category="confirmed_settled",
    event_date=date(2026, 1, 1),
    settlement_date=None,
):
    return NormalizedEvent(
        event_id=event_id,
        user_id="user_test",
        event_type="expense",
        category="other",
        description=event_id,
        direction=direction,
        amount=amount,
        currency="USD",
        event_date=event_date,
        settlement_date=settlement_date or event_date,
        status=status_category,
        status_category=status_category,
        flexibility="fixed",
        minimum_allowed_amount=None,
        linked_event_id=None,
        recurrence_key=None,
        recurrence_rule=None,
        recurrence_explicit=False,
        reconciled_event=None,
        sort_key=(event_date, event_date, event_id),
    )


class TestForecast(unittest.TestCase):
    request_date = date(2026, 1, 1)

    def test_request_date_opening_balance(self):
        result = simulate_90_day_forecast(profile(), [], self.request_date)
        self.assertEqual(result.daily_balances[0].opening_balance, Decimal("100.00"))

    def test_exactly_90_dates_and_final_date(self):
        result = simulate_90_day_forecast(profile(), [], self.request_date)
        self.assertEqual(len(result.daily_balances), 90)
        self.assertEqual(result.end_date, self.request_date + timedelta(days=89))
        self.assertEqual(result.daily_balances[-1].date, result.end_date)

    def test_single_inflow(self):
        result = simulate_90_day_forecast(
            profile(), [event("income", Decimal("20"), "credit")], self.request_date
        )
        self.assertEqual(result.daily_balances[0].inflows, Decimal("20"))
        self.assertEqual(result.daily_balances[0].closing_balance, Decimal("120.00"))

    def test_single_outflow(self):
        result = simulate_90_day_forecast(
            profile(), [event("expense", Decimal("20"))], self.request_date
        )
        self.assertEqual(result.daily_balances[0].outflows, Decimal("20"))
        self.assertEqual(result.daily_balances[0].closing_balance, Decimal("80.00"))

    def test_multiple_events_on_one_day_are_stable(self):
        result = simulate_90_day_forecast(
            profile(),
            [event("b", Decimal("10")), event("a", Decimal("20"), "credit")],
            self.request_date,
        )
        self.assertEqual(result.daily_balances[0].applied_event_ids, ["a", "b"])
        self.assertEqual(result.daily_balances[0].closing_balance, Decimal("110.00"))

    def test_multiple_days_of_events(self):
        later = self.request_date + timedelta(days=2)
        result = simulate_90_day_forecast(
            profile(), [event("later", Decimal("30"), event_date=later)], self.request_date
        )
        self.assertEqual(result.daily_balances[2].closing_balance, Decimal("70.00"))

    def test_events_outside_window_are_ignored(self):
        before = event("before", event_date=self.request_date - timedelta(days=1))
        after = event("after", event_date=self.request_date + timedelta(days=90))
        result = simulate_90_day_forecast(profile(), [before, after], self.request_date)
        self.assertEqual(result.daily_balances[-1].closing_balance, Decimal("100.00"))

    def test_statuses_not_affecting_balance(self):
        events = [
            event(status, Decimal("10"), status_category=status)
            for status in ("pending", "failed", "cancelled", "estimate")
        ]
        result = simulate_90_day_forecast(profile(), events, self.request_date)
        self.assertEqual(result.daily_balances[0].closing_balance, Decimal("90.00"))

    def test_confirmed_and_settled_events_affect_balance(self):
        result = simulate_90_day_forecast(
            profile(),
            [event("confirmed", Decimal("10"), status_category="future_confirmed")],
            self.request_date,
        )
        self.assertEqual(result.daily_balances[0].closing_balance, Decimal("90.00"))

    def test_settlement_date_controls_movement(self):
        settlement = self.request_date + timedelta(days=3)
        result = simulate_90_day_forecast(
            profile(), [event("settled", settlement_date=settlement)], self.request_date
        )
        self.assertEqual(result.daily_balances[0].closing_balance, Decimal("100.00"))
        self.assertEqual(result.daily_balances[3].closing_balance, Decimal("90.00"))

    def test_missing_amount_is_skipped_and_recorded(self):
        result = simulate_90_day_forecast(
            profile(), [event("unknown", amount=None)], self.request_date
        )
        self.assertEqual(result.daily_balances[0].closing_balance, Decimal("100.00"))
        self.assertEqual(result.skipped_event_ids, ["unknown"])

    def test_decimal_arithmetic_and_minimum_metadata(self):
        result = simulate_90_day_forecast(
            profile(minimum=Decimal("33.33")),
            [event("precise", Decimal("0.01"))],
            self.request_date,
        )
        self.assertEqual(result.daily_balances[0].closing_balance, Decimal("99.99"))
        self.assertEqual(result.minimum_balance_required, Decimal("33.33"))

    def test_empty_event_list(self):
        result = simulate_90_day_forecast(profile(), [], self.request_date)
        self.assertEqual(result.minimum_projected_balance, Decimal("100.00"))
        self.assertEqual(result.minimum_balance_date, self.request_date)

    def test_zero_amount_edge_case(self):
        result = simulate_90_day_forecast(
            profile(), [event("zero", Decimal("0"))], self.request_date
        )
        self.assertEqual(result.daily_balances[0].outflows, Decimal("0"))

    def test_minimum_projected_balance_and_date(self):
        lower = self.request_date + timedelta(days=5)
        result = simulate_90_day_forecast(
            profile(),
            [event("lower", Decimal("70"), event_date=lower)],
            self.request_date,
        )
        self.assertEqual(result.minimum_projected_balance, Decimal("30.00"))
        self.assertEqual(result.minimum_balance_date, lower)


if __name__ == "__main__":
    unittest.main()
