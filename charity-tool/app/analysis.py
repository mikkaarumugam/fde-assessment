"""Trend + hot-prospect logic.

Pure functions, no network — this is the part the sales team's decisions hinge
on, so it's isolated here and unit-tested in tests/test_analysis.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

# A charity's income/expenditure wobbles year to year. We only call it a real
# trend once the change over the window exceeds this dead-band; inside it, "flat".
TREND_DEADBAND = 0.02  # +/- 2%

# The sales team's headline signal: income jumped >10% versus the prior year.
HOT_PROSPECT_THRESHOLD = 0.10  # 10% year-on-year


def parse_period_end(date_str: Optional[str]):
    """Parse the API's '2023-03-31T00:00:00' into a date. None if unparseable."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "")).date()
    except (ValueError, AttributeError):
        return None


def last_n_years(history: list[dict], n: int = 3) -> list[dict]:
    """Normalise raw financial-history rows and return the latest `n`, oldest first.

    Each returned row: {label, year, period_end, income, expenditure}.
    """
    rows = []
    for entry in history or []:
        period_end = parse_period_end(entry.get("financial_period_end_date"))
        if period_end is None:
            continue
        rows.append(
            {
                "period_end": period_end.isoformat(),
                "year": period_end.year,
                # ar_cycle_reference e.g. 'AR23'; fall back to the calendar year.
                "label": entry.get("ar_cycle_reference") or str(period_end.year),
                "income": entry.get("income"),
                "expenditure": entry.get("expenditure"),
            }
        )
    rows.sort(key=lambda r: r["period_end"])
    return rows[-n:]


def pct_change(old: Optional[float], new: Optional[float]) -> Optional[float]:
    """Fractional change old->new (0.10 == +10%). None if not computable."""
    if old is None or new is None or old == 0:
        return None
    return (new - old) / abs(old)


def trend(values: list[Optional[float]]) -> tuple[str, Optional[float]]:
    """Trend across a series (oldest -> newest): compare first vs last value.

    Returns (direction, fractional_change) where direction is
    'up' | 'flat' | 'down' | 'unknown'.
    """
    nums = [v for v in values if v is not None]
    if len(nums) < 2:
        return "unknown", None
    change = pct_change(nums[0], nums[-1])
    if change is None:
        return "unknown", None
    if change > TREND_DEADBAND:
        return "up", change
    if change < -TREND_DEADBAND:
        return "down", change
    return "flat", change


def hot_prospect(income_values: list[Optional[float]]) -> tuple[bool, Optional[float]]:
    """Hot if the most recent year's income is >10% above the prior year."""
    nums = [v for v in income_values if v is not None]
    if len(nums) < 2:
        return False, None
    change = pct_change(nums[-2], nums[-1])
    if change is None:
        return False, None
    return change > HOT_PROSPECT_THRESHOLD, change


def summarise_financials(rows: list[dict]) -> dict:
    """Given normalised rows (oldest first), compute trends + hot-prospect flag."""
    income = [r["income"] for r in rows]
    expenditure = [r["expenditure"] for r in rows]

    income_trend, income_change = trend(income)
    expenditure_trend, expenditure_change = trend(expenditure)
    is_hot, hot_change = hot_prospect(income)

    return {
        "income_trend": income_trend,
        "income_change": income_change,
        "expenditure_trend": expenditure_trend,
        "expenditure_change": expenditure_change,
        "hot_prospect": is_hot,
        "hot_prospect_change": hot_change,
    }
