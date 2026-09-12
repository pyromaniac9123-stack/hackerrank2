import unittest
from copy import deepcopy
from datetime import date
from decimal import Decimal

from code.forecast import simulate_90_day_forecast
from code.models import FinancialProfile, Request
from code.safety import evaluate_safety


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


def request(amount):
    return Request(
        request_id="request_test",
        user_id="user_test",
        request_date=date(2026, 1, 1),
        request_type="purchase",
        requested_amount=amount,
        desired_completion_date=None,
        allows_partial_payment=False,
        request_text=None,
    )


def forecast_for(profile_value, event_list=()):
    return simulate_90_day_forecast(
        profile_value, event_list, date(2026, 1, 1)
    )


class TestSafety(unittest.TestCase):
    def test_available_margin_is_safe_and_capped_by_request(self):
        result = evaluate_safety(
            request(Decimal("50.00")),
            profile(),
            forecast_for(profile()),
        )
        self.assertEqual(result.amount_safe_to_pay, Decimal("50.00"))
        self.assertTrue(result.is_current_request_fully_safe)

    def test_future_obligation_reduces_safe_amount(self):
        from tests.test_forecast import event

        result = evaluate_safety(
            request(Decimal("100.00")),
            profile(),
            forecast_for(
                profile(),
                [event("future", Decimal("60"), event_date=date(2026, 1, 2))],
            ),
        )
        self.assertEqual(result.amount_safe_to_pay, Decimal("15.00"))
        self.assertEqual(result.minimum_projected_balance_before_purchase, Decimal("40.00"))
        self.assertEqual(result.minimum_projected_balance_after_purchase, Decimal("25.00"))
        self.assertFalse(result.is_current_request_fully_safe)

    def test_future_inflow_increases_safe_amount(self):
        from tests.test_forecast import event

        result = evaluate_safety(
            request(Decimal("100.00")),
            profile(),
            forecast_for(
                profile(),
                [
                    event("income", Decimal("100"), "credit", event_date=date(2026, 1, 2)),
                    event("future", Decimal("60"), event_date=date(2026, 1, 3)),
                ],
            ),
        )
        self.assertEqual(result.amount_safe_to_pay, Decimal("75.00"))

    def test_exact_minimum_boundary_is_safe(self):
        result = evaluate_safety(
            request(Decimal("75.00")),
            profile(),
            forecast_for(profile()),
        )
        self.assertEqual(result.amount_safe_to_pay, Decimal("75.00"))
        self.assertEqual(result.minimum_projected_balance_after_purchase, Decimal("25.00"))

    def test_current_balance_below_minimum_returns_zero(self):
        low_profile = profile(balance=Decimal("20.00"))
        result = evaluate_safety(request(Decimal("1.00")), low_profile, forecast_for(low_profile))
        self.assertEqual(result.amount_safe_to_pay, Decimal("0"))
        self.assertFalse(result.is_current_request_fully_safe)

    def test_zero_request(self):
        result = evaluate_safety(request(Decimal("0")), profile(), forecast_for(profile()))
        self.assertEqual(result.amount_safe_to_pay, Decimal("0"))
        self.assertTrue(result.is_current_request_fully_safe)

    def test_decimal_precision(self):
        precise_profile = profile(
            balance=Decimal("100.00"), minimum=Decimal("33.33")
        )
        result = evaluate_safety(
            request(Decimal("66.67")),
            precise_profile,
            forecast_for(precise_profile),
        )
        self.assertEqual(result.amount_safe_to_pay, Decimal("66.67"))

    def test_forecast_is_not_mutated(self):
        forecast = forecast_for(profile())
        before = deepcopy(forecast)
        evaluate_safety(request(Decimal("10.00")), profile(), forecast)
        self.assertEqual(forecast, before)

    def test_optional_profile_preferences_do_not_change_safety(self):
        base = profile()
        changed = profile()
        changed.expense_categories_user_is_willing_to_stop.append("subscriptions")
        first = evaluate_safety(request(Decimal("100")), base, forecast_for(base))
        second = evaluate_safety(request(Decimal("100")), changed, forecast_for(changed))
        self.assertEqual(first.amount_safe_to_pay, second.amount_safe_to_pay)

    def test_missing_and_negative_request_amounts_fail(self):
        with self.assertRaises(ValueError):
            evaluate_safety(request(None), profile(), forecast_for(profile()))
        with self.assertRaises(ValueError):
            evaluate_safety(request(Decimal("-1")), profile(), forecast_for(profile()))

    def test_forecast_requirement_mismatch_fails(self):
        forecast = forecast_for(profile())
        forecast.minimum_balance_required = Decimal("99")
        with self.assertRaises(ValueError):
            evaluate_safety(request(Decimal("1")), profile(), forecast)


if __name__ == "__main__":
    unittest.main()
