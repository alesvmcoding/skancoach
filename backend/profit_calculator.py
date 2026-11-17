"""Extract the profit amount from a hunt title as profit per hour."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


PROFIT_RE = re.compile(
    r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<unit>kk|k)"
    r"(?P<before_hour>\s*/\s*h)?\s*(?:\([^)]*\)\s*)?\+?\s*"
    r"(?P<kind>Profit|Waste)\b(?P<after_hour>\s*/\s*h)?",
    re.IGNORECASE,
)
PROFIT_AFTER_RE = re.compile(
    r"\b(?P<kind>Profit|Waste)\b\s*[:=\-]?\s*(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<unit>kk|k)"
    r"(?P<after_hour>\s*/\s*h)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Profit:
    value_per_hour: float | None
    display: str | None
    source_display: str | None
    assumption: str | None


def _format_rate(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    absolute = abs(value)
    if absolute >= Decimal(1_000_000):
        amount, unit = absolute / Decimal(1_000_000), "kk"
    elif absolute >= Decimal(1_000):
        amount, unit = absolute / Decimal(1_000), "k"
    else:
        amount, unit = absolute, ""
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{sign}{format(amount, 'f').rstrip('0').rstrip('.')}{unit}/h"


def extract_profit(title: str) -> Profit:
    """Get the first amount explicitly associated with Profit.

    If the title omits `/h`, the amount is treated as the result of a one-hour
    hunt, per the user's rule.
    """
    match = PROFIT_RE.search(title or "") or PROFIT_AFTER_RE.search(title or "")
    if not match:
        return Profit(None, None, None, None)
    amount = Decimal(match.group("amount").replace(",", "."))
    unit = match.group("unit").lower()
    value = amount * (Decimal(1_000_000) if unit == "kk" else Decimal(1_000))
    groups = match.groupdict()
    if groups.get("kind", "Profit").casefold() == "waste":
        value = -value
    explicit_hour = bool(groups.get("before_hour") or groups.get("after_hour"))
    assumption = None if explicit_hour else "Sem /h no título; assumido resultado de 1 hora."
    source = match.group(0).strip()
    return Profit(float(value), _format_rate(value), source, assumption)
