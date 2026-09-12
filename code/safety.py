from decimal import Decimal

from code.models import ForecastResult, FinancialProfile, Request, SafetyResult


def evaluate_safety(
    request: Request,
    profile: FinancialProfile,
    forecast: ForecastResult,
) -> SafetyResult:
    """Return the maximum request-date payment before optional changes."""
    requested_amount = request.requested_amount
    if requested_amount is None:
        raise ValueError(
            f"Request {request.request_id} has no requested amount"
        )
    if requested_amount < Decimal("0"):
        raise ValueError(
            f"Request {request.request_id} has a negative requested amount"
        )
    if forecast.minimum_balance_required != profile.minimum_balance_to_keep:
        raise ValueError(
            "Forecast minimum balance requirement does not match profile"
        )

    before = forecast.minimum_projected_balance
    available_margin = before - profile.minimum_balance_to_keep
    safe_amount = min(requested_amount, max(Decimal("0"), available_margin))
    after = before - safe_amount
    return SafetyResult(
        amount_safe_to_pay=safe_amount,
        minimum_projected_balance_before_purchase=before,
        minimum_projected_balance_after_purchase=after,
        minimum_balance_required=profile.minimum_balance_to_keep,
        is_current_request_fully_safe=safe_amount == requested_amount,
        limiting_date=forecast.minimum_balance_date,
    )
