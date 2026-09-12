import unittest
from datetime import date, timedelta
from decimal import Decimal

from code.forecast import simulate_90_day_forecast
from code.models import (
    FinancialProfile,
    FinancialEvent,
    NormalizedEvent,
    PaymentOption,
    Request,
)
from code.planner import generate_payment_plans
from code.safety import evaluate_safety


def profile(methods=None, balance=Decimal("100.00"), minimum=Decimal("25.00")):
    return FinancialProfile(
        "user_test", "USD", balance, minimum, [], [], [], [], methods or ["full_payment"], None
    )


def request(amount=Decimal("50.00"), allows=False, deadline=None):
    return Request("request_test", "user_test", date(2026, 1, 1), "purchase", amount, deadline, allows, None)


def event(event_id, amount, day=1, **kwargs):
    event_date = date(2026, 1, day)
    original = FinancialEvent(
        event_id, "user_test", "expense", event_id, "subscriptions", "debit",
        amount, "USD", event_date, event_date, "settled", None,
        kwargs.get("flexibility", "fixed"), kwargs.get("minimum_allowed_amount"),
    )
    return NormalizedEvent(
        event_id, "user_test", "expense", "subscriptions", event_id, "debit",
        amount, "USD", event_date, event_date, kwargs.get("status_category", "confirmed_settled"),
        kwargs.get("status_category", "confirmed_settled"), kwargs.get("flexibility", "fixed"),
        kwargs.get("minimum_allowed_amount"), None, None, None, False, None,
        (event_date, event_date, event_id),
    )


def context(profile_value, events=()):
    forecast = simulate_90_day_forecast(profile_value, events, date(2026, 1, 1))
    safety = evaluate_safety(request(Decimal("50")), profile_value, forecast)
    return forecast, safety


class TestPlanner(unittest.TestCase):
    def test_full_payment_today_when_safe(self):
        p = profile()
        forecast, safety = context(p)
        result = generate_payment_plans(request(), p, [], forecast, safety)
        self.assertTrue(any(plan.feasible and plan.completion_date == date(2026, 1, 1) for plan in result.feasible_plans))

    def test_full_payment_unsafe_today_and_later_payment(self):
        p = profile(balance=Decimal("50"))
        future = event("expense", Decimal("20"), day=2)
        forecast, safety = context(p, [future])
        result = generate_payment_plans(request(Decimal("20")), p, [future], forecast, safety)
        self.assertIsNone(result.earliest_full_payment_date)

    def test_partial_payment_exactly_two_installments(self):
        p = profile(["partial_payment"])
        future = event("income", Decimal("60"), day=2)
        future.direction = "credit"
        forecast, safety = context(
            profile(["partial_payment"], balance=Decimal("40")), [future]
        )
        result = generate_payment_plans(
            request(Decimal("50"), True, date(2026, 1, 10)),
            profile(["partial_payment"], balance=Decimal("40")),
            [future],
            forecast,
            safety,
        )
        partial = [plan for plan in result.candidate_plans if plan.payment_method == "partial_payment"]
        self.assertEqual(len(partial), 1)
        self.assertEqual(len(partial[0].installments), 2)
        self.assertEqual(partial[0].total_amount, Decimal("50"))

    def test_partial_payment_requires_permission(self):
        p = profile(["full_payment"])
        forecast, safety = context(p)
        result = generate_payment_plans(request(Decimal("50"), True), p, [], forecast, safety)
        self.assertFalse(any(plan.payment_method == "partial_payment" for plan in result.candidate_plans))

    def test_supplied_installment_must_be_exact_and_feasible(self):
        p = profile(["installments"])
        forecast, safety = context(p)
        option = PaymentOption("po1", "request_test", "installments", Decimal("25"), 2, date(2026, 1, 1), 7, Decimal("0"), Decimal("50"))
        result = generate_payment_plans(request(), p, [], forecast, safety, [option])
        installment = [plan for plan in result.candidate_plans if plan.payment_option_id == "po1"][0]
        self.assertTrue(installment.feasible)
        self.assertEqual([item.amount for item in installment.installments], [Decimal("25"), Decimal("25")])

    def test_infeasible_installment_is_rejected(self):
        p = profile(["installments"], balance=Decimal("40"))
        forecast, safety = context(p)
        option = PaymentOption("po1", "request_test", "installments", Decimal("30"), 2, date(2026, 1, 1), 7, None, Decimal("60"))
        result = generate_payment_plans(request(Decimal("60")), p, [], forecast, safety, [option])
        self.assertFalse(result.feasible_plans)

    def test_no_invented_options_and_dates_unchanged(self):
        p = profile(["installments"])
        forecast, safety = context(p)
        result = generate_payment_plans(request(), p, [], forecast, safety, [])
        self.assertFalse(any(plan.payment_option_id for plan in result.candidate_plans))

    def test_spending_change_stop_is_limited_and_eligible(self):
        p = profile(["full_payment"])
        p.expense_categories_user_is_willing_to_stop = ["subscriptions"]
        recurring = event("sub", Decimal("80"), day=2, flexibility="stoppable")
        recurring.recurrence_explicit = True
        forecast, safety = context(p, [recurring])
        result = generate_payment_plans(request(Decimal("100")), p, [recurring], forecast, safety)
        self.assertTrue(any("stop:sub" in plan.spending_changes for plan in result.candidate_plans))

    def test_protected_or_nonrecurring_expense_cannot_change(self):
        p = profile(["full_payment"])
        fixed = event("fixed", Decimal("80"), day=2, flexibility="fixed")
        forecast, safety = context(p, [fixed])
        result = generate_payment_plans(request(Decimal("100")), p, [fixed], forecast, safety)
        self.assertFalse(any(plan.spending_changes for plan in result.candidate_plans))

    def test_spending_change_reduce_to_uses_minimum_allowed_amount(self):
        p = profile(["full_payment"])
        p.expense_categories_user_is_willing_to_reduce = ["subscriptions"]
        recurring = event(
            "sub_reduce",
            Decimal("80"),
            day=2,
            flexibility="reducible",
            minimum_allowed_amount=Decimal("20"),
        )
        recurring.recurrence_explicit = True
        forecast, safety = context(p, [recurring])
        result = generate_payment_plans(request(Decimal("100")), p, [recurring], forecast, safety)
        self.assertTrue(
            any(
                "reduce_to:sub_reduce:20" in plan.spending_changes
                for plan in result.candidate_plans
            )
        )

    def test_plans_do_not_mutate_forecast(self):
        p = profile()
        forecast, safety = context(p)
        before = repr(forecast)
        generate_payment_plans(request(), p, [], forecast, safety)
        self.assertEqual(repr(forecast), before)

    def test_zero_and_invalid_request(self):
        p = profile()
        forecast, safety = context(p)
        result = generate_payment_plans(request(Decimal("0")), p, [], forecast, safety)
        self.assertTrue(result.feasible_plans)
        with self.assertRaises(ValueError):
            generate_payment_plans(request(None), p, [], forecast, safety)


if __name__ == "__main__":
    unittest.main()
