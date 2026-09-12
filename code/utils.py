from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional

from code.models import ExchangeRate

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


def convert_amount(
    amount: Decimal,
    from_currency: str,
    to_currency: str,
    rate_date: date,
    rates: Iterable[ExchangeRate],
) -> Decimal:
    """Convert using the dated table, allowing an inverse or a short rate chain."""
    source, target = from_currency.upper(), to_currency.upper()
    if source == target:
        return amount
    available_dates = sorted({r.rate_date for r in rates if r.rate_date <= rate_date})
    chosen_date = available_dates[-1] if available_dates else None
    dated = [r for r in rates if r.rate_date == chosen_date]
    graph: dict[str, list[tuple[str, Decimal]]] = {}
    for rate in dated:
        a, b = rate.from_currency.upper(), rate.to_currency.upper()
        graph.setdefault(a, []).append((b, rate.rate))
        if rate.rate:
            graph.setdefault(b, []).append((a, Decimal("1") / rate.rate))
    queue: list[tuple[str, Decimal]] = [(source, Decimal("1"))]
    visited = {source}
    while queue:
        currency, factor = queue.pop(0)
        for nxt, edge in graph.get(currency, []):
            if nxt in visited:
                continue
            product = factor * edge
            if nxt == target:
                return amount * product
            visited.add(nxt)
            queue.append((nxt, product))
    raise ValueError(f"No exchange rate for {source}->{target} on {rate_date}")
