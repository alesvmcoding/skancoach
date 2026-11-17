"""Extract XP/hour from a title and normalize it to the 100% Raw rate."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


RATE_RE = re.compile(
    r"(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<unit>kk|k)(?P<per_hour>\s*(?:/\s*h|h))?",
    re.IGNORECASE,
)
PERCENT_RE = re.compile(r"(?<!\w)(?P<percent>\d+(?:[.,]\d+)?)\s*%")
RAW_RE = re.compile(r"\braw\b", re.IGNORECASE)
XP_LABEL_RE = re.compile(r"\b(?:xp|exp)\b", re.IGNORECASE)
EXTRA_MODIFIER_RE = re.compile(r"\b(?:prey|book\s+boosted)\b", re.IGNORECASE)


@dataclass(frozen=True)
class RawXp:
    raw_value: float | None
    raw_display: str | None
    source_display: str | None
    multiplier_percent: float | None
    status: str
    note: str | None


def _format_rate(value: Decimal) -> str:
    if value >= Decimal(1_000_000):
        amount = value / Decimal(1_000_000)
        unit = "kk"
    elif value >= Decimal(1_000):
        amount = value / Decimal(1_000)
        unit = "k"
    else:
        amount = value
        unit = ""
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    amount_text = format(rounded, "f").rstrip("0").rstrip(".")
    return f"{amount_text}{unit}/h"


def calculate_raw_xp(title: str) -> RawXp:
    """Normalize a title XP rate to 100%; preserve its source and assumptions.

    Profit values are excluded. Explicit Raw rates are kept unchanged. If the
    title has no percentage and no Raw marker, a 150% basis is assumed and
    clearly flagged, per the user's rule.
    """
    text = title or ""
    rate_match = None
    percent_match = PERCENT_RE.search(text)
    raw_marked = RAW_RE.search(text) is not None
    xp_labeled = XP_LABEL_RE.search(text) is not None
    for match in RATE_RE.finditer(text):
        before = text[max(0, match.start() - 12):match.start()]
        after = text[match.end():match.end() + 12]
        if re.search(r"profit\s*[:=\-]?\s*$", before, re.IGNORECASE) or re.match(
            r"\s*profit\b", after, re.IGNORECASE
        ):
            continue
        # A bare amount can still be the XP rate when the title explicitly
        # states a percentage or labels the amount Raw. Profit tokens above
        # remain excluded.
        if not match.group("per_hour") and not percent_match and not raw_marked and not xp_labeled:
            continue
        rate_match = match
        break

    if rate_match is None:
        return RawXp(None, None, None, None, "not_found", "No XP/h rate found in title")

    amount = Decimal(rate_match.group("amount").replace(",", "."))
    unit = rate_match.group("unit").lower()
    source_value = amount * (Decimal(1_000_000) if unit == "kk" else Decimal(1_000))
    percent = Decimal(percent_match.group("percent").replace(",", ".")) if percent_match else None
    source_display = f"{rate_match.group(0).replace(' ', '')}"
    if raw_marked:
        raw_value = source_value
        status = "already_raw"
        note = "O título já identifica o valor como Raw."
        effective_percent = percent or Decimal(100)
    elif percent and percent > 0:
        raw_value = source_value * Decimal(100) / percent
        effective_percent = percent
        if EXTRA_MODIFIER_RE.search(text):
            status = "calculated_with_modifier"
            note = "O título também cita Prey/Book Boosted; o bônus extra não foi separado."
        else:
            status = "calculated"
            note = f"Calculada a partir de {percent}%: XP do título ÷ {percent / Decimal(100)}."
    else:
        effective_percent = Decimal(150)
        raw_value = source_value * Decimal(100) / effective_percent
        status = "assumed_150"
        note = "O título não informa percentual nem Raw; 150% foi presumido."

    source_display += f" ({percent_match.group('percent')}%)" if percent_match else (" Raw" if raw_marked else " (150% presumido)")
    raw_value = raw_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return RawXp(
        raw_value=float(raw_value),
        raw_display=_format_rate(raw_value),
        source_display=source_display,
        multiplier_percent=float(effective_percent),
        status=status,
        note=note,
    )
