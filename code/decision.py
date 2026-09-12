from decimal import Decimal

from code.models import FinalDecision, PaymentPlan, PlannerResult, Request, SafetyResult


def _format_amount(amount: Decimal) -> str:
    return format(amount, "f")


def _format_plan(plan: PaymentPlan) -> str:
    return "|".join(
        f"{installment.payment_date.isoformat()}:{_format_amount(installment.amount)}"
        for installment in sorted(plan.installments, key=lambda item: item.payment_date)
    )


def _within_deadline(plan: PaymentPlan, request: Request) -> bool:
    return (
        request.desired_completion_date is None
        or plan.completion_date <= request.desired_completion_date
    )


def _is_later_full_payment(plan: PaymentPlan, request: Request) -> bool:
    return (
        plan.payment_method == "full_payment"
        and len(plan.installments) == 1
        and plan.total_amount == request.requested_amount
        and plan.completion_date > request.request_date
    )


def _empty_decision(amount: Decimal, earliest: str, explanation: str) -> FinalDecision:
    return FinalDecision(
        amount_safe_to_pay=amount,
        affordability_status="not_affordable",
        recommended_payment_method="not_recommended",
        payment_plan="none",
        earliest_date_for_full_payment=earliest,
        spending_changes_needed="none",
        decision_explanation=explanation,
    )


def decide(
    request: Request,
    safety: SafetyResult,
    planner: PlannerResult,
) -> FinalDecision:
    """Convert already-computed safety and plan results into final output fields."""
    requested = request.requested_amount
    if requested is None or requested < Decimal("0"):
        raise ValueError(f"Request {request.request_id} has an invalid amount")
    if safety.amount_safe_to_pay < Decimal("0") or safety.amount_safe_to_pay > requested:
        raise ValueError(
            f"Safety result for {request.request_id} is outside the request amount"
        )

    earliest = (
        planner.earliest_full_payment_date.isoformat()
        if planner.earliest_full_payment_date is not None
        else ""
    )
    safe_now = safety.amount_safe_to_pay == requested
    if safe_now:
        earliest = request.request_date.isoformat()
    feasible = [
        plan for plan in planner.feasible_plans if _within_deadline(plan, request)
    ]

    if safe_now:
        today = [
            plan
            for plan in feasible
            if plan.completion_date == request.request_date
            and plan.total_amount == requested
            and not _is_later_full_payment(plan, request)
        ]
        if today:
            selected = today[0]
            return FinalDecision(
                safety.amount_safe_to_pay,
                "affordable_now",
                selected.payment_method,
                _format_plan(selected),
                earliest,
                "|".join(selected.spending_changes) or "none",
                f"Pay {_format_amount(requested)} in full today; "
                f"{_format_amount(safety.amount_safe_to_pay)} is safe to pay now.",
            )

    plan_candidates = [
        plan for plan in feasible if not _is_later_full_payment(plan, request)
    ]
    if plan_candidates and not safe_now:
        selected = plan_candidates[0]
        return FinalDecision(
            safety.amount_safe_to_pay,
            "affordable_with_plan",
            selected.payment_method,
            _format_plan(selected),
            earliest,
            "|".join(selected.spending_changes) or "none",
            f"{_format_amount(requested)} is not safe to pay today, "
            f"but the selected {selected.payment_method} plan completes it safely.",
        )

    later = [
        plan
        for plan in feasible
        if _is_later_full_payment(plan, request)
    ]
    if not safe_now and later:
        selected = later[0]
        return FinalDecision(
            safety.amount_safe_to_pay,
            "affordable_later",
            "wait",
            _format_plan(selected),
            earliest,
            "none",
            f"Wait until {selected.completion_date.isoformat()} to pay "
            f"{_format_amount(requested)} in full safely.",
        )

    return _empty_decision(
        safety.amount_safe_to_pay,
        earliest,
        f"Do not pay {_format_amount(requested)}; no permitted safe solution "
        "is available within the applicable constraints.",
    )


def make_decision(
    request: Request,
    safety: SafetyResult,
    planner: PlannerResult,
) -> FinalDecision:
    """Descriptive alias for callers that prefer an explicit operation name."""
    return decide(request, safety, planner)
