import unittest
import csv
import os
from pathlib import Path
from code.data_loader import load_requests, load_financial_profiles, load_financial_events, load_exchange_rates, load_payment_options, load_messages, load_images
from code.models import Request, FinancialProfile, FinancialEvent, ExchangeRate, PaymentOption, Message, ImageRecord

class TestDataLoader(unittest.TestCase):
    def setUp(self):
        self.dataset_path = Path("dataset/requests.csv")
        self.profile_dataset_path = Path("dataset/financial_profiles.csv")
        self.images_dataset_path = Path("dataset/images.csv")
        self.media_root = Path("dataset/media/images")
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
    def test_load_actual_messages(self):
        messages = load_messages(Path("dataset/messages.csv"))
        self.assertIsInstance(messages, dict)
        self.assertGreater(len(messages), 0)
        for mid, msg in messages.items():
            self.assertIsInstance(msg, Message)
            self.assertEqual(mid, msg.message_id)

    def test_message_text_preservation(self):
        path = self.tmp_dir / "msg_test.csv"
        with open(path, "w", newline="", encoding='utf-8') as f:
            fields = ['message_id', 'user_id', 'request_id', 'related_event_id', 'sent_at', 'source_type', 'message_text']
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            text = "Hello! 123 @#$%^&*()_+ {}:\"|<>? \n \t "
            writer.writerow({
                'message_id': 'm1', 'user_id': 'u1', 'request_id': '', 'related_event_id': '',
                'sent_at': '2025-01-01T10:00:00Z', 'source_type': 'test', 'message_text': text
            })
        
        messages = load_messages(path)
        self.assertEqual(messages['m1'].message_text, text)

        
        with self.assertRaises(ValueError):
            load_payment_options(path)

    def test_load_actual_images(self):
        images = load_images(self.images_dataset_path)
        self.assertIsInstance(images, dict)
        self.assertEqual(len(images), 16)
        self.assertIsInstance(images["image_01"], ImageRecord)
        self.assertEqual(images["image_01"].media_reference, "image_01.png")
        self.assertEqual(images["image_16"].related_event_id, "event_10521")

    def test_validate_actual_image_media(self):
        images = load_images(self.images_dataset_path, self.media_root)
        self.assertEqual(images["image_07"].media_path, self.media_root / "image_07.png")
        self.assertTrue(all(record.media_path.is_file() for record in images.values()))

    def test_missing_images_csv(self):
        with self.assertRaises(FileNotFoundError):
            load_images(self.tmp_dir / "missing_images.csv")

    def test_images_missing_required_column(self):
        path = self.tmp_dir / "missing_image_column.csv"
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(["image_id", "user_id", "request_id"])
        with self.assertRaises(ValueError):
            load_images(path)

    def test_duplicate_image_id(self):
        path = self.tmp_dir / "duplicate_images.csv"
        fields = ["image_id", "user_id", "request_id", "related_event_id"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            row = dict(zip(fields, ["image_01", "user_01", "", ""]))
            writer.writerow(row)
            writer.writerow(row)
        with self.assertRaisesRegex(ValueError, "Duplicate image_id"):
            load_images(path)

    def test_blank_optional_image_fields_are_none(self):
        path = self.tmp_dir / "blank_image_fields.csv"
        fields = ["image_id", "user_id", "request_id", "related_event_id"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerow({
                "image_id": "image_blank",
                "user_id": "user_01",
                "request_id": "",
                "related_event_id": " ",
            })
        record = load_images(path)["image_blank"]
        self.assertIsNone(record.request_id)
        self.assertIsNone(record.related_event_id)

    def test_missing_referenced_media_file(self):
        path = self.tmp_dir / "missing_media.csv"
        fields = ["image_id", "user_id", "request_id", "related_event_id"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerow({
                "image_id": "image_missing",
                "user_id": "user_01",
                "request_id": "",
                "related_event_id": "",
            })
        with self.assertRaisesRegex(FileNotFoundError, "image_missing"):
            load_images(path, self.tmp_dir)



if __name__ == "__main__":
    unittest.main()
