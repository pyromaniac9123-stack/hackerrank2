import unittest
from datetime import date
from decimal import Decimal

from code.decision import decide
from code.models import (
    PaymentInstallment,
    PaymentPlan,
    PlannerResult,
    Request,
    SafetyResult,
)


DAY = date(2026, 1, 1)


def request(amount=Decimal("100"), deadline=None):
    return Request("r1", "u1", DAY, "purchase", amount, deadline, True, None)


def plan(
    method="full_payment",
    dates=(DAY,),
    amounts=(Decimal("100"),),
    changes=(),
    option=None,
):
    installments = [
        PaymentInstallment(payment_date, amount)
        for payment_date, amount in zip(dates, amounts)
    ]
    return PaymentPlan(
        installments,
        method,
        option,
        list(changes),
        sum(amounts, Decimal("0")),
        max(dates),
        True,
        "minimum balance preserved",
    )


def context(amount=Decimal("100"), safe=Decimal("0"), earliest=None, plans=()):
    safety = SafetyResult(safe, Decimal("20"), Decimal("20"), Decimal("20"), safe == amount, DAY)
    return safety, PlannerResult(list(plans), list(plans), earliest)


class TestDecision(unittest.TestCase):
    def test_affordable_now_prefers_full_payment(self):
        safety, planner = context(
            safe=Decimal("100"),
            plans=[plan("full_payment"), plan("installments", (DAY, date(2026, 1, 8)), (Decimal("50"), Decimal("50")))],
        )
        result = decide(request(), safety, planner)
        self.assertEqual(result.affordability_status, "affordable_now")
        self.assertEqual(result.recommended_payment_method, "full_payment")
        self.assertEqual(result.payment_plan, "2026-01-01:100")

    def test_partial_plan_is_affordable_with_plan(self):
        later = date(2026, 1, 5)
        selected = plan("partial_payment", (DAY, later), (Decimal("40"), Decimal("60")))
        safety, planner = context(safe=Decimal("40"), earliest=later, plans=[selected])
        result = decide(request(deadline=date(2026, 1, 10)), safety, planner)
        self.assertEqual(result.affordability_status, "affordable_with_plan")
        self.assertEqual(result.recommended_payment_method, "partial_payment")
        self.assertEqual(result.payment_plan, "2026-01-01:40|2026-01-05:60")

    def test_installments_are_consumed_not_invented(self):
        selected = plan("installments", (date(2026, 1, 3), date(2026, 1, 10)), (Decimal("50"), Decimal("50")), option="po1")
        safety, planner = context(safe=Decimal("0"), plans=[selected])
        result = decide(request(deadline=date(2026, 1, 10)), safety, planner)
        self.assertEqual(result.recommended_payment_method, "installments")
        self.assertEqual(result.payment_plan, "2026-01-03:50|2026-01-10:50")

    def test_spending_changes_are_copied_exactly(self):
        selected = plan(changes=("stop:event_1", "reduce_to:event_2:20"))
        safety, planner = context(safe=Decimal("0"), plans=[selected])
        result = decide(request(), safety, planner)
        self.assertEqual(result.spending_changes_needed, "stop:event_1|reduce_to:event_2:20")

    def test_later_full_payment_becomes_wait(self):
        later = date(2026, 1, 7)
        selected = plan(dates=(later,))
        safety, planner = context(safe=Decimal("25"), earliest=later, plans=[selected])
        result = decide(request(deadline=date(2026, 1, 10)), safety, planner)
        self.assertEqual(result.affordability_status, "affordable_later")
        self.assertEqual(result.recommended_payment_method, "wait")
        self.assertEqual(result.earliest_date_for_full_payment, "2026-01-07")

    def test_unaffordable_has_no_plan(self):
        safety, planner = context(safe=Decimal("0"))
        result = decide(request(), safety, planner)
        self.assertEqual(result.affordability_status, "not_affordable")
        self.assertEqual(result.recommended_payment_method, "not_recommended")
        self.assertEqual(result.payment_plan, "none")
        self.assertEqual(result.spending_changes_needed, "none")

    def test_earliest_date_is_independent_of_preferences(self):
        later = date(2026, 1, 4)
        safety, planner = context(safe=Decimal("0"), earliest=later)
        result = decide(request(), safety, planner)
        self.assertEqual(result.earliest_date_for_full_payment, "2026-01-04")

    def test_empty_earliest_date_and_decimal_formatting(self):
        selected = plan("full_payment", amounts=(Decimal("620.40"),))
        safety, planner = context(amount=Decimal("620.40"), safe=Decimal("620.40"), plans=[selected])
        result = decide(request(Decimal("620.40")), safety, planner)
        self.assertEqual(result.payment_plan, "2026-01-01:620.40")
        self.assertEqual(result.earliest_date_for_full_payment, "2026-01-01")

    def test_invalid_safety_result_is_rejected(self):
        safety, planner = context(safe=Decimal("101"))
        with self.assertRaises(ValueError):
            decide(request(), safety, planner)

    def test_decision_is_deterministic(self):
        selected = plan(changes=("stop:event_1",))
        safety, planner = context(safe=Decimal("0"), plans=[selected])
        self.assertEqual(decide(request(), safety, planner), decide(request(), safety, planner))

    def test_zero_safe_amount_is_preserved(self):
        safety, planner = context(safe=Decimal("0"))
        result = decide(request(), safety, planner)
        self.assertEqual(result.amount_safe_to_pay, Decimal("0"))

    def test_zero_request_can_be_paid_now(self):
        selected = plan(amounts=(Decimal("0"),))
        safety, planner = context(amount=Decimal("0"), safe=Decimal("0"), plans=[selected])
        result = decide(request(Decimal("0")), safety, planner)
        self.assertEqual(result.affordability_status, "affordable_now")
        self.assertEqual(result.payment_plan, "2026-01-01:0")

    def test_exact_minimum_balance_safe_payment_is_accepted(self):
        selected = plan()
        safety, planner = context(safe=Decimal("100"), plans=[selected])
        result = decide(request(), safety, planner)
        self.assertEqual(result.affordability_status, "affordable_now")

    def test_later_plan_after_deadline_is_not_selected(self):
        later = date(2026, 1, 7)
        selected = plan(dates=(later,))
        safety, planner = context(safe=Decimal("0"), earliest=later, plans=[selected])
        result = decide(request(deadline=date(2026, 1, 5)), safety, planner)
        self.assertEqual(result.affordability_status, "not_affordable")
        self.assertEqual(result.payment_plan, "none")

    def test_no_plan_is_invented_from_earliest_date(self):
        later = date(2026, 1, 7)
        safety, planner = context(safe=Decimal("0"), earliest=later)
        result = decide(request(deadline=date(2026, 1, 10)), safety, planner)
        self.assertEqual(result.affordability_status, "not_affordable")
        self.assertEqual(result.payment_plan, "none")

    def test_ranked_feasible_plan_is_used(self):
        first = plan("installments", (DAY, date(2026, 1, 2)), (Decimal("50"), Decimal("50")), option="a")
        second = plan("installments", (DAY, date(2026, 1, 3)), (Decimal("50"), Decimal("50")), option="b")
        safety, planner = context(safe=Decimal("0"), plans=[first, second])
        result = decide(request(), safety, planner)
        self.assertEqual(result.payment_plan, "2026-01-01:50|2026-01-02:50")

    def test_explanation_is_stable_and_human_readable(self):
        later = date(2026, 1, 7)
        selected = plan(dates=(later,))
        safety, planner = context(safe=Decimal("25"), earliest=later, plans=[selected])
        result = decide(request(), safety, planner)
        self.assertEqual(
            result.decision_explanation,
            "Wait until 2026-01-07 to pay 100 in full safely.",
        )

    def test_payment_plan_amounts_sum_to_request(self):
        selected = plan("partial_payment", (DAY, date(2026, 1, 2)), (Decimal("40"), Decimal("60")))
        safety, planner = context(safe=Decimal("40"), plans=[selected])
        result = decide(request(), safety, planner)
        amounts = [Decimal(item.split(":")[1]) for item in result.payment_plan.split("|")]
        self.assertEqual(sum(amounts, Decimal("0")), Decimal("100"))


if __name__ == "__main__":
    unittest.main()
