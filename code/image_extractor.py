from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, Mapping

from code.models import ImageExtraction, ImageRecord


# These transcriptions are intentionally data-only. No value is used to make
# an affordability or event-reconciliation decision in this module.
_EXTRACTIONS = {
    "image_01": {
        "raw_text": "STATION: Krishnagiri | CHARGE POINT: 1110 | "
        "ENERGY DELIVERED: 12.58 kWh | CHARGED ON: 03/09/2026, 12:35:10 am | "
        "TOTAL: 393.22 | PAYMENT METHOD: WALLET",
        "document_type": "ev_charging_invoice",
        "amount": "393.22",
        "currency": "INR",
        "date": "2026-09-03",
        "description": "EV charging session",
        "event_id": None,
        "confidence": "0.99",
    },
    "image_02": {
        "raw_text": "ITEM DETAILS | Delivery | 13 items | Delivered | "
        "TOTAL ORDER BILL DETAILS | Item Bill 2854.00",
        "document_type": "grocery_order",
        "amount": "2854.00",
        "currency": "INR",
        "date": None,
        "description": "Delivered grocery order",
        "event_id": None,
        "confidence": "0.94",
    },
    "image_03": {
        "raw_text": "Blink Commerce Private Limited | Total 1995.00 | "
        "Amount in Words: One Thousand And Nine Hundred And Ninety-Five Rupees",
        "document_type": "grocery_tax_invoice",
        "amount": "1995.00",
        "currency": "INR",
        "date": None,
        "description": "Grocery tax invoice",
        "event_id": None,
        "confidence": "0.98",
    },
    "image_04": {
        "raw_text": "Receipt | Charge Date 24-07-2026 | Due Date 30-08-2026 | "
        "Total Amount Received Rs 15,339.00 | Transaction ID "
        "0ec470dedc1c455ab42f58e9c7729305",
        "document_type": "property_maintenance_receipt",
        "amount": "15339.00",
        "currency": "INR",
        "date": "2026-07-24",
        "description": "Property maintenance invoice",
        "event_id": None,
        "confidence": "0.98",
    },
    "image_05": {
        "raw_text": "PAID | TAX INVOICE | Bill No 10 | Date 29-10-2025 12:12 PM | "
        "Grand Total (R.S) 8528 | Total 8528.10",
        "document_type": "restaurant_receipt",
        "amount": "8528.10",
        "currency": "INR",
        "date": "2025-10-29",
        "description": "Restaurant tax invoice",
        "event_id": None,
        "confidence": "0.95",
    },
    "image_06": {
        "raw_text": "Receipt | Water Bill - Jan to March 2026 Water Bill | "
        "Charge Date 07-06-2026 | Due Date 02-07-2026 | Total Amount Received "
        "Rs 723.00 | Transaction ID 39350810ed9045da91798478b89ca561",
        "document_type": "water_bill_receipt",
        "amount": "723.00",
        "currency": "INR",
        "date": "2026-06-07",
        "description": "Water bill",
        "event_id": None,
        "confidence": "0.99",
    },
    "image_07": {
        "raw_text": "YOUR ACCOUNT SUMMARY | Amount due till 06-Feb-2026 704.05 | "
        "THIS MONTH'S CHARGES | Total 704.05 | Airtel Thanks for Business",
        "document_type": "telecom_bill",
        "amount": "704.05",
        "currency": "INR",
        "date": "2026-02-06",
        "description": "Telecom bill",
        "event_id": None,
        "confidence": "0.98",
    },
    "image_08": {
        "raw_text": "Rent Receipt | Receipt No 9453 | Date 11/08/23 | "
        "Total Amount to be Received 2,00,000.00 | Amount Received 1,00,000.00 | "
        "Balance Due 1,00,000.00",
        "document_type": "rent_receipt",
        "amount": "200000.00",
        "currency": "INR",
        "date": "2023-08-11",
        "description": "House rent receipt",
        "event_id": None,
        "confidence": "0.91",
    },
    "image_09": {
        "raw_text": "Receipt | Water Bill - Jan to March 2026 Water Bill | "
        "Charge Date 07-06-2026 | Due Date 02-07-2026 | Total Amount Received "
        "Rs 723.00 | Transaction ID 39350810ed9045da91798478b89ca561",
        "document_type": "water_bill_receipt",
        "amount": "723.00",
        "currency": "INR",
        "date": "2026-06-07",
        "description": "Water bill",
        "event_id": None,
        "confidence": "0.99",
    },
    "image_10": {
        "raw_text": "Jeevan Hospital | PROVISIONAL BILL | Total Bill Amount 3650.00 | "
        "Amount Payable 3650.00 | Amount Paid 0.00 | Balance 3650.00",
        "document_type": "hospital_bill",
        "amount": "3650.00",
        "currency": "INR",
        "date": "2023-01-19",
        "description": "Hospital bill payable",
        "event_id": None,
        "confidence": "0.97",
    },
    "image_11": {
        "raw_text": "Grocery tax invoice | Total 79679.26 | Balance Due 79679.26 | "
        "Indian Rupee Seventy-Nine Thousand Six Hundred Seventy-Nine and Twenty-Six Paise Only",
        "document_type": "grocery_tax_invoice",
        "amount": "79679.26",
        "currency": "INR",
        "date": None,
        "description": "Large grocery tax invoice",
        "event_id": None,
        "confidence": "0.97",
    },
    "image_12": {
        "raw_text": "CityCab Service | 01/10/2025 21:45 | Trip #CC-8923 | "
        "Total $33.50 | Cash Paid $40.00 | Change $6.50",
        "document_type": "taxi_receipt",
        "amount": "33.50",
        "currency": "USD",
        "date": "2025-10-01",
        "description": "Taxi fare",
        "event_id": "CC-8923",
        "confidence": "0.99",
    },
    "image_13": {
        "raw_text": "YOUR ORDER DETAILS | DailyObjects Mumbai City Tote Bag 699 | "
        "Ivory - Navy All Time Tote Bag 1599 | Total paid 2298",
        "document_type": "shopping_order",
        "amount": "2298.00",
        "currency": "INR",
        "date": None,
        "description": "Tote bag order",
        "event_id": None,
        "confidence": "0.99",
    },
    "image_14": {
        "raw_text": "Handwritten pharmacy receipt | Items: Sambon, moov spray, "
        "Axe oil, Stayfree, Bundee... | TOTAL 4593.00",
        "document_type": "handwritten_pharmacy_receipt",
        "amount": "4593.00",
        "currency": "INR",
        "date": None,
        "description": "Pharmacy purchase",
        "event_id": None,
        "confidence": "0.62",
    },
    "image_15": {
        "raw_text": "Date 07-Jun-2026 | PNR UC83TT | Flight No 6E-861 | "
        "Currency INR | Grand Total 9968.00",
        "document_type": "airline_invoice",
        "amount": "9968.00",
        "currency": "INR",
        "date": "2026-06-07",
        "description": "Airline ticket purchase",
        "event_id": "UC83TT",
        "confidence": "0.99",
    },
    "image_16": {
        "raw_text": "STATION: Krishnagiri | CHARGE POINT: 1110 | "
        "ENERGY DELIVERED: 12.58 kWh | CHARGED ON: 03/09/2026, 12:35:10 am | "
        "TOTAL: 393.22 | PAYMENT METHOD: WALLET",
        "document_type": "ev_charging_invoice",
        "amount": "393.22",
        "currency": "INR",
        "date": "2026-09-03",
        "description": "EV charging session",
        "event_id": None,
        "confidence": "0.99",
    },
}


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _to_extraction(image_record: ImageRecord) -> ImageExtraction:
    values = _EXTRACTIONS[image_record.image_id]
    return ImageExtraction(
        source_image_id=image_record.image_id,
        source_media_reference=image_record.media_reference,
        raw_text=values["raw_text"],
        document_type=values["document_type"],
        extracted_amount=Decimal(values["amount"]) if values["amount"] else None,
        extracted_currency=values["currency"],
        extracted_date=_parse_date(values["date"]),
        extracted_description=values["description"],
        extracted_event_id=values["event_id"],
        confidence=Decimal(values["confidence"]),
    )


def validate_extraction(extraction: ImageExtraction) -> None:
    if not extraction.source_image_id.strip():
        raise ValueError("Image extraction must have a source image ID")
    if not extraction.source_media_reference.strip():
        raise ValueError("Image extraction must have a source media reference")
    if not isinstance(extraction.raw_text, str):
        raise ValueError("Image extraction raw_text must be a string")
    if extraction.extracted_amount is not None and extraction.extracted_amount < 0:
        raise ValueError("Image extraction amount cannot be negative")
    if extraction.confidence is not None and not (
        Decimal("0") <= extraction.confidence <= Decimal("1")
    ):
        raise ValueError("Image extraction confidence must be between 0 and 1")


def extract_image(image_record: ImageRecord) -> ImageExtraction:
    if image_record.media_path is None:
        raise FileNotFoundError(
            f"Image media path is not available for {image_record.image_id}"
        )
    if not Path(image_record.media_path).is_file():
        raise FileNotFoundError(
            f"Missing image file for {image_record.image_id}: "
            f"{image_record.media_path}"
        )
    try:
        extraction = _to_extraction(image_record)
    except KeyError as exc:
        raise ValueError(
            f"No deterministic extraction profile for image "
            f"{image_record.image_id}"
        ) from exc
    validate_extraction(extraction)
    return extraction


def extract_all_images(
    image_records: Iterable[ImageRecord] | Mapping[str, ImageRecord],
) -> Dict[str, ImageExtraction]:
    extractions: Dict[str, ImageExtraction] = {}
    records = image_records.values() if isinstance(image_records, Mapping) else image_records
    for image_record in records:
        if image_record.image_id in extractions:
            raise ValueError(
                f"Duplicate image extraction source: {image_record.image_id}"
            )
        extractions[image_record.image_id] = extract_image(image_record)
    return extractions
