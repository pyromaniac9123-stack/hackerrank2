import unittest
import csv
import os
from pathlib import Path
from code.data_loader import load_requests, load_financial_profiles, load_financial_events, load_exchange_rates, load_payment_options
from code.models import Request, FinancialProfile, FinancialEvent, ExchangeRate, PaymentOption

class TestDataLoader(unittest.TestCase):
    def setUp(self):
        self.dataset_path = Path("dataset/requests.csv")
        self.profile_dataset_path = Path("dataset/financial_profiles.csv")
        self.tmp_dir = Path("tests/tmp")
        self.tmp_dir.mkdir(exist_ok=True)

    def tearDown(self):
        for f in self.tmp_dir.glob("*"):
            f.unlink()
        if self.tmp_dir.exists():
            self.tmp_dir.rmdir()

    def test_load_actual_dataset(self):
        requests = load_requests(self.dataset_path)
        self.assertIsInstance(requests, dict)
        self.assertEqual(len(requests), 250)
        for rid, req in requests.items():
            self.assertIsInstance(req, Request)
            self.assertEqual(rid, req.request_id)

    def test_load_actual_profile_dataset(self):
        profiles = load_financial_profiles(self.profile_dataset_path)
        self.assertIsInstance(profiles, dict)
        self.assertEqual(len(profiles), 275)
        for uid, prof in profiles.items():
            self.assertIsInstance(prof, FinancialProfile)
            self.assertEqual(uid, prof.user_id)

    def test_missing_column(self):
        path = self.tmp_dir / "missing.csv"
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["request_id", "user_id"])
        
        with self.assertRaises(ValueError):
            load_requests(path)

    def test_duplicate_id(self):
        path = self.tmp_dir / "duplicate.csv"
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=['request_id', 'user_id', 'request_date', 'request_type', 'requested_amount', 'desired_completion_date', 'allows_partial_payment', 'request_text'])
            writer.writeheader()
            row = {'request_id': '1', 'user_id': 'u1', 'request_date': '2025-08-08', 'request_type': 't', 'requested_amount': '10', 'desired_completion_date': '2025-09-09', 'allows_partial_payment': 'true', 'request_text': 'text'}
            writer.writerow(row)
            writer.writerow(row)
        
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            load_requests(path)

    def test_invalid_data(self):
        path = self.tmp_dir / "invalid.csv"
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=['request_id', 'user_id', 'request_date', 'request_type', 'requested_amount', 'desired_completion_date', 'allows_partial_payment', 'request_text'])
            writer.writeheader()
            writer.writerow({'request_id': '1', 'user_id': 'u1', 'request_date': 'invalid-date', 'request_type': 't', 'requested_amount': '10', 'desired_completion_date': '2025-09-09', 'allows_partial_payment': 'true', 'request_text': 'text'})
        
        with self.assertRaises(ValueError):
            load_requests(path)
    
    def test_invalid_profile_numeric(self):
        path = self.tmp_dir / "invalid_profile.csv"
        with open(path, "w", newline="") as f:
            fields = ['user_id', 'home_currency', 'current_available_balance', 'minimum_balance_to_keep',
                      'financial_priorities', 'expense_categories_to_protect', 
                      'expense_categories_user_is_willing_to_reduce', 'expense_categories_user_is_willing_to_stop',
                      'payment_methods_user_will_consider', 'max_installment_months']
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerow({'user_id': 'u1', 'home_currency': 'ZAR', 'current_available_balance': 'invalid', 'minimum_balance_to_keep': '100', 'financial_priorities': '', 'expense_categories_to_protect': '', 'expense_categories_user_is_willing_to_reduce': '', 'expense_categories_user_is_willing_to_stop': '', 'payment_methods_user_will_consider': '', 'max_installment_months': ''})
        
        with self.assertRaises(ValueError):
            load_financial_profiles(path)
    def test_load_actual_events(self):
        events = load_financial_events(Path("dataset/financial_events.csv"))
        self.assertIsInstance(events, dict)
        self.assertGreater(len(events), 0)
        for eid, event in events.items():
            self.assertIsInstance(event, FinancialEvent)
            self.assertEqual(eid, event.event_id)
    def test_load_actual_exchange_rates(self):
        rates = load_exchange_rates(Path("dataset/exchange_rates.csv"))
        self.assertIsInstance(rates, list)
        self.assertGreater(len(rates), 0)
        for rate in rates:
            self.assertIsInstance(rate, ExchangeRate)

    def test_invalid_exchange_rate(self):
        path = self.tmp_dir / "invalid_rate.csv"
        with open(path, "w", newline="") as f:
            fields = ['rate_date', 'from_currency', 'to_currency', 'rate']
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerow({'rate_date': '2023-10-15', 'from_currency': 'EUR', 'to_currency': 'ZAR', 'rate': 'invalid'})
        
        with self.assertRaises(ValueError):
            load_exchange_rates(path)

    def test_load_actual_payment_options(self):
        options = load_payment_options(Path("dataset/request_payment_options.csv"))
        self.assertIsInstance(options, dict)
        self.assertGreater(len(options), 0)
        for poid, option in options.items():
            self.assertIsInstance(option, PaymentOption)
            self.assertEqual(poid, option.payment_option_id)

    def test_invalid_payment_option_monetary(self):
        path = self.tmp_dir / "invalid_option.csv"
        with open(path, "w", newline="") as f:
            fields = ['payment_option_id', 'request_id', 'payment_method', 'payment_amount',
                      'number_of_payments', 'first_payment_date', 'payment_frequency_days',
                      'financing_fee', 'total_payable_amount']
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerow({
                'payment_option_id': 'po1', 'request_id': 'r1', 'payment_method': 'full_payment',
                'payment_amount': 'invalid', 'number_of_payments': '1', 'first_payment_date': '2024-03-03',
                'payment_frequency_days': '', 'financing_fee': '0', 'total_payable_amount': '100'
            })
        
        with self.assertRaises(ValueError):
            load_payment_options(path)



if __name__ == "__main__":
    unittest.main()
