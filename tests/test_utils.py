import unittest
from datetime import date
from decimal import Decimal
from code.utils import parse_decimal, parse_date

class TestUtils(unittest.TestCase):
    def test_parse_decimal(self):
        self.assertEqual(parse_decimal("123.45"), Decimal("123.45"))
        self.assertEqual(parse_decimal(""), None)
        self.assertEqual(parse_decimal(None), None)
        self.assertEqual(parse_decimal("   "), None)
        with self.assertRaises(ValueError):
            parse_decimal("invalid")

    def test_parse_date(self):
        self.assertEqual(parse_date("2025-08-08"), date(2025, 8, 8))
        self.assertEqual(parse_date(""), None)
        self.assertEqual(parse_date(None), None)
        self.assertEqual(parse_date("   "), None)
        with self.assertRaises(ValueError):
            parse_date("invalid")

if __name__ == "__main__":
    unittest.main()
