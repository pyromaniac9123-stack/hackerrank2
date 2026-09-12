import unittest
from datetime import datetime
from decimal import Decimal

from code.data_loader import load_financial_events, load_messages
from code.event_normalizer import normalize_events
from code.message_cashflows import message_cash_flows
from code.models import FinancialEvent, Message


def message(text, message_id="message_test"):
    return Message(
        message_id=message_id,
        user_id="user_test",
        request_id=None,
        related_event_id=None,
        sent_at=datetime(2026, 1, 1),
        source_type="employer",
        message_text=text,
    )


class TestMessageCashFlows(unittest.TestCase):
    def test_explicit_amount_and_date_create_one_flow(self):
        result = message_cash_flows(
            [message("Salary will be EUR 1661 on 2026-01-15")], []
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].canonical_amount, Decimal("1661"))
        self.assertEqual(result[0].canonical_currency, "EUR")
        self.assertEqual(result[0].canonical_event_date.isoformat(), "2026-01-15")
        self.assertEqual(result[0].original_event.direction, "credit")
        self.assertEqual(result[0].amount_source, "message:message_test")

    def test_real_salary_messages_create_credits(self):
        messages = load_messages("dataset/messages.csv")
        result = message_cash_flows(
            [messages["message_10"], messages["message_11"]], []
        )
        self.assertEqual(
            {flow.evidence_sources[0]: flow.original_event.direction for flow in result},
            {"message:message_10": "credit", "message:message_11": "credit"},
        )

    def test_date_without_amount_creates_nothing(self):
        self.assertEqual(
            message_cash_flows([message("Salary resumes on 2026-01-15")], []),
            [],
        )

    def test_amount_without_date_creates_nothing(self):
        self.assertEqual(
            message_cash_flows([message("Salary will be EUR 1661")], []),
            [],
        )

    def test_childcare_without_amount_creates_nothing(self):
        self.assertEqual(
            message_cash_flows(
                [message("A recurring childcare payment begins on 2026-01-15")],
                [],
            ),
            [],
        )

    def test_cancelled_message_creates_nothing(self):
        self.assertEqual(
            message_cash_flows(
                [message("Cancelled salary payment EUR 1661 on 2026-01-15")],
                [],
            ),
            [],
        )

    def test_equivalent_event_prevents_duplicate(self):
        event = FinancialEvent(
            event_id="event_existing",
            user_id="user_test",
            event_type="income",
            description="Salary",
            category="salary",
            direction="credit",
            amount=Decimal("1661"),
            currency="EUR",
            event_date=datetime(2026, 1, 15).date(),
            settlement_date=datetime(2026, 1, 15).date(),
            status="scheduled",
            linked_event_id=None,
            flexibility="fixed",
            minimum_allowed_amount=None,
        )
        normalized = normalize_events(
            [
                type("Reconciled", (), {
                    "event_id": event.event_id,
                    "original_event": event,
                    "canonical_amount": event.amount,
                    "canonical_currency": event.currency,
                    "canonical_event_date": event.event_date,
                    "canonical_settlement_date": event.settlement_date,
                    "canonical_status": event.status,
                    "canonical_description": event.description,
                })()
            ]
        )
        self.assertEqual(
            message_cash_flows(
                [message("Salary will be EUR 1661 on 2026-01-15")],
                [item.reconciled_event for item in normalized.values()],
            ),
            [],
        )

    def test_single_message_does_not_become_recurring(self):
        result = message_cash_flows(
            [message("Salary will be EUR 1661 on 2026-01-15")], []
        )
        self.assertFalse(result[0].canonical_description == "monthly")

    def test_real_messages_create_only_explicit_flows(self):
        messages = load_messages("dataset/messages.csv")
        events = load_financial_events("dataset/financial_events.csv")
        normalized = normalize_events(
            [
                type("Reconciled", (), {
                    "event_id": event.event_id,
                    "original_event": event,
                    "canonical_amount": event.amount,
                    "canonical_currency": event.currency,
                    "canonical_event_date": event.event_date,
                    "canonical_settlement_date": event.settlement_date,
                    "canonical_status": event.status,
                    "canonical_description": event.description,
                })()
                for event in events.values()
            ]
        )
        flows = message_cash_flows(messages, [item.reconciled_event for item in normalized.values()])
        by_id = {flow.evidence_sources[0]: flow for flow in flows}
        self.assertEqual(by_id["message:message_10"].canonical_amount, Decimal("2717"))
        self.assertEqual(by_id["message:message_10"].canonical_event_date.isoformat(), "2025-08-15")
        self.assertEqual(by_id["message:message_11"].canonical_amount, Decimal("1661"))
        self.assertEqual(by_id["message:message_11"].canonical_event_date.isoformat(), "2026-01-15")
        self.assertNotIn("message:message_05", by_id)


if __name__ == "__main__":
    unittest.main()
