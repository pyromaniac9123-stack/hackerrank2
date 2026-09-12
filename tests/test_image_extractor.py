import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from code.data_loader import load_financial_events, load_images
from code.image_extractor import (
    extract_all_images,
    extract_image,
    validate_extraction,
)
from code.models import ImageExtraction


class TestImageExtractor(unittest.TestCase):
    def setUp(self):
        self.media_root = Path("dataset/media/images")
        self.records = load_images(Path("dataset/images.csv"), self.media_root)

    def test_all_real_images_are_processed(self):
        extractions = extract_all_images(self.records.values())
        self.assertEqual(len(extractions), 16)

    def test_source_ids_and_representative_values(self):
        extractions = extract_all_images(self.records.values())
        self.assertEqual(extractions["image_05"].source_image_id, "image_05")
        self.assertEqual(extractions["image_05"].extracted_amount, Decimal("8528.10"))
        self.assertEqual(extractions["image_12"].extracted_event_id, "CC-8923")
        self.assertEqual(extractions["image_15"].extracted_date.isoformat(), "2026-06-07")

    def test_money_and_dates_use_typed_values(self):
        extraction = extract_image(self.records["image_16"])
        self.assertIsInstance(extraction.extracted_amount, Decimal)
        self.assertIsInstance(extraction.extracted_date, date)

    def test_raw_text_and_uncertainty_are_preserved(self):
        extraction = extract_image(self.records["image_14"])
        self.assertIn("Handwritten pharmacy receipt", extraction.raw_text)
        self.assertIsNone(extraction.extracted_date)
        self.assertEqual(extraction.confidence, Decimal("0.62"))

    def test_extractor_does_not_modify_financial_events(self):
        events = load_financial_events(Path("dataset/financial_events.csv"))
        before = replace(events["event_10521"])
        extract_all_images(self.records.values())
        self.assertEqual(events["event_10521"], before)

    def test_image_text_is_data_not_executable_instruction(self):
        extraction = extract_image(self.records["image_13"])
        self.assertNotIn("affordable_now", extraction.raw_text)
        self.assertEqual(extraction.extracted_amount, Decimal("2298.00"))

    def test_missing_image_is_clear(self):
        missing = replace(
            self.records["image_01"],
            media_path=self.media_root / "does-not-exist.png",
        )
        with self.assertRaisesRegex(FileNotFoundError, "image_01"):
            extract_image(missing)

    def test_malformed_extraction_is_rejected(self):
        malformed = ImageExtraction(
            source_image_id="image_bad",
            source_media_reference="image_bad.png",
            raw_text="",
            document_type=None,
            extracted_amount=Decimal("-1"),
            extracted_currency=None,
            extracted_date=None,
            extracted_description=None,
            extracted_event_id=None,
            confidence=Decimal("1.1"),
        )
        with self.assertRaises(ValueError):
            validate_extraction(malformed)


if __name__ == "__main__":
    unittest.main()
