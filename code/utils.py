from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

def parse_decimal(value: str | None) -> Decimal | None:
    if value is None or value.strip() == "":
        return None
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        raise ValueError(f"Invalid decimal value: {value}")

def parse_date(value: str | None) -> date | None:
    if value is None or value.strip() == "":
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(f"Invalid date value: {value}")

def parse_datetime(value: str | None):
    if value is None or value.strip() == "":
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(f"Invalid datetime value: {value}")

