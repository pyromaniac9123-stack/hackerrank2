from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

@dataclass
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: Optional[Decimal]
    desired_completion_date: Optional[date]
    allows_partial_payment: bool
    request_text: Optional[str]

@dataclass
class FinancialProfile:
    user_id: str
    home_currency: str
    current_available_balance: Decimal
    minimum_balance_to_keep: Decimal
    financial_priorities: list[str]
    expense_categories_to_protect: list[str]
    expense_categories_user_is_willing_to_reduce: list[str]
    expense_categories_user_is_willing_to_stop: list[str]
    payment_methods_user_will_consider: list[str]
    max_installment_months: Optional[int]

@dataclass
class FinancialEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: Optional[Decimal]
    currency: str
    event_date: date
    settlement_date: date
    status: str
    linked_event_id: Optional[str]
    flexibility: str
    minimum_allowed_amount: Optional[Decimal]

@dataclass
class ExchangeRate:
    rate_date: date
    from_currency: str
    to_currency: str
    rate: Decimal

@dataclass
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: Optional[Decimal]
    number_of_payments: Optional[int]
    first_payment_date: Optional[date]
    payment_frequency_days: Optional[int]
    financing_fee: Optional[Decimal]
    total_payable_amount: Optional[Decimal]

@dataclass
class Message:
    message_id: str
    user_id: str
    request_id: Optional[str]
    related_event_id: Optional[str]
    sent_at: datetime
    source_type: str
    message_text: str

@dataclass
class ImageRecord:
    image_id: str
    user_id: str
    request_id: Optional[str]
    related_event_id: Optional[str]
    media_reference: str
    media_path: Optional[Path]


@dataclass
class ImageExtraction:
    source_image_id: str
    source_media_reference: str
    raw_text: str
    document_type: Optional[str]
    extracted_amount: Optional[Decimal]
    extracted_currency: Optional[str]
    extracted_date: Optional[date]
    extracted_description: Optional[str]
    extracted_event_id: Optional[str]
    confidence: Optional[Decimal]


@dataclass
class NormalizedFinancialEvent:
    event_id: str
    original_event: FinancialEvent
    canonical_amount: Optional[Decimal]
    canonical_currency: str
    canonical_event_date: date
    canonical_settlement_date: date
    canonical_status: str
    canonical_description: str
    amount_source: str
    currency_source: str
    status_source: str
    description_source: str
    recovered_from_evidence: bool
    evidence_sources: list[str]
    reconciliation_notes: list[str]


@dataclass
class NormalizedEvent:
    event_id: str
    user_id: str
    event_type: str
    category: str
    description: str
    direction: str
    amount: Optional[Decimal]
    currency: str
    event_date: Optional[date]
    settlement_date: Optional[date]
    status: str
    status_category: str
    flexibility: str
    minimum_allowed_amount: Optional[Decimal]
    linked_event_id: Optional[str]
    recurrence_key: Optional[str]
    recurrence_rule: Optional[str]
    recurrence_explicit: bool
    reconciled_event: NormalizedFinancialEvent
    sort_key: tuple[date, date, str]
    recurrence_source_event_id: Optional[str] = None
    occurrence_date: Optional[date] = None


@dataclass
class DailyBalance:
    date: date
    opening_balance: Decimal
    inflows: Decimal
    outflows: Decimal
    closing_balance: Decimal
    applied_event_ids: list[str]


@dataclass
class ForecastResult:
    request_date: date
    end_date: date
    minimum_balance_required: Decimal
    daily_balances: list[DailyBalance]
    minimum_projected_balance: Decimal
    minimum_balance_date: date
    skipped_event_ids: list[str]


@dataclass
class SafetyResult:
    amount_safe_to_pay: Decimal
    minimum_projected_balance_before_purchase: Decimal
    minimum_projected_balance_after_purchase: Decimal
    minimum_balance_required: Decimal
    is_current_request_fully_safe: bool
    limiting_date: date


@dataclass
class PaymentInstallment:
    payment_date: date
    amount: Decimal


@dataclass
class PaymentPlan:
    installments: list[PaymentInstallment]
    payment_method: str
    payment_option_id: Optional[str]
    spending_changes: list[str]
    total_amount: Decimal
    completion_date: date
    feasible: bool
    feasibility_reason: str


@dataclass
class PlannerResult:
    candidate_plans: list[PaymentPlan]
    feasible_plans: list[PaymentPlan]
    earliest_full_payment_date: Optional[date]


@dataclass
class FinalDecision:
    amount_safe_to_pay: Decimal
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: str
    spending_changes_needed: str
    decision_explanation: str
