import csv
import hashlib
import re
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from code.main import OUTPUT_FIELDS, run

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"
VALID_STATUSES = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
VALID_METHODS = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = TemporaryDirectory()
        cls.output = Path(cls.tempdir.name) / "output.csv"
        cls.decisions = run(DATASET, cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def rows(self):
        with self.output.open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_output_schema_and_request_coverage(self):
        rows = self.rows()
        with (DATASET / "requests.csv").open(encoding="utf-8", newline="") as stream:
            requests = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 250)
        self.assertEqual(list(rows[0]), OUTPUT_FIELDS)
        self.assertEqual([row["request_id"] for row in rows], [row["request_id"] for row in requests])
        self.assertEqual(len({row["request_id"] for row in rows}), 250)

    def test_values_and_serialization_are_valid(self):
        requests = {request.request_id: request for request, _ in self.decisions}
        for row in self.rows():
            self.assertIn(row["affordability_status"], VALID_STATUSES)
            self.assertIn(row["recommended_payment_method"], VALID_METHODS)
            self.assertNotIn(row["amount_safe_to_pay"], {"", "None", "NaN"})
            Decimal(row["amount_safe_to_pay"])
            self.assertNotRegex(",".join(row.values()), r"Decimal\(|None|NaN")
            if row["payment_plan"] == "none":
                self.assertEqual(row["recommended_payment_method"], "not_recommended")
            else:
                total = Decimal("0")
                for payment in row["payment_plan"].split("|"):
                    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}):(-?\d+(?:\.\d+)?)", payment)
                    self.assertIsNotNone(match)
                    total += Decimal(match.group(2))
                self.assertEqual(total, requests[row["request_id"]].requested_amount)
            for change in row["spending_changes_needed"].split("|"):
                if change != "none":
                    self.assertRegex(change, r"^(stop:[^|]+|reduce_to:[^|:]+:-?\d+(?:\.\d+)?)$")

    def test_repeated_run_is_identical(self):
        first = self.output.read_bytes()
        with TemporaryDirectory() as directory:
            second_path = Path(directory) / "output.csv"
            run(DATASET, second_path)
            self.assertEqual(hashlib.sha256(first).digest(), hashlib.sha256(second_path.read_bytes()).digest())


if __name__ == "__main__":
    unittest.main()
