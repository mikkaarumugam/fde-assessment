"""Unit tests for the trend + hot-prospect logic. No network."""

from app.analysis import (
    hot_prospect,
    last_n_years,
    summarise_financials,
    trend,
)


def _year(end_date, income, expenditure, ar=None):
    return {
        "financial_period_end_date": end_date,
        "income": income,
        "expenditure": expenditure,
        "ar_cycle_reference": ar,
    }


# ---- trend ----

def test_trend_up_beyond_deadband():
    direction, change = trend([100, 110, 130])
    assert direction == "up"
    assert round(change, 2) == 0.30


def test_trend_down_beyond_deadband():
    direction, _ = trend([200, 150, 120])
    assert direction == "down"


def test_trend_flat_within_deadband():
    # +1% overall -> inside the 2% dead-band -> flat, not up.
    direction, _ = trend([100, 105, 101])
    assert direction == "flat"


def test_trend_unknown_with_insufficient_data():
    assert trend([100])[0] == "unknown"
    assert trend([None, None])[0] == "unknown"


def test_trend_ignores_none_values():
    direction, _ = trend([100, None, 130])
    assert direction == "up"


# ---- hot prospect ----

def test_hot_prospect_when_latest_year_jumps():
    is_hot, change = hot_prospect([100, 100, 115])  # +15% latest YoY
    assert is_hot is True
    assert round(change, 2) == 0.15


def test_not_hot_when_growth_under_threshold():
    is_hot, _ = hot_prospect([100, 100, 105])  # +5%
    assert is_hot is False


def test_not_hot_exactly_at_threshold():
    # Strictly greater than 10% required.
    is_hot, _ = hot_prospect([100, 100, 110])
    assert is_hot is False


def test_hot_prospect_uses_latest_two_years_only():
    # Big early jump, flat recent year -> not currently hot.
    is_hot, _ = hot_prospect([100, 200, 205])
    assert is_hot is False


# ---- last_n_years ----

def test_last_n_years_sorts_and_trims():
    history = [
        _year("2023-03-31T00:00:00", 130, 120, "AR23"),
        _year("2021-03-31T00:00:00", 100, 90, "AR21"),
        _year("2022-03-31T00:00:00", 110, 100, "AR22"),
        _year("2020-03-31T00:00:00", 80, 70, "AR20"),
    ]
    rows = last_n_years(history, n=3)
    assert [r["label"] for r in rows] == ["AR21", "AR22", "AR23"]
    assert rows[-1]["income"] == 130


def test_last_n_years_skips_unparseable_dates():
    history = [
        _year(None, 100, 90),
        _year("2022-03-31T00:00:00", 110, 100, "AR22"),
    ]
    rows = last_n_years(history, n=3)
    assert len(rows) == 1
    assert rows[0]["label"] == "AR22"


# ---- summarise_financials (integration of the above) ----

def test_summarise_flags_growing_charity_as_hot():
    history = [
        _year("2021-03-31T00:00:00", 100, 95, "AR21"),
        _year("2022-03-31T00:00:00", 105, 100, "AR22"),
        _year("2023-03-31T00:00:00", 130, 110, "AR23"),  # +23.8% YoY
    ]
    rows = last_n_years(history, n=3)
    summary = summarise_financials(rows)
    assert summary["income_trend"] == "up"
    assert summary["hot_prospect"] is True
    assert summary["expenditure_trend"] == "up"


def test_summarise_handles_empty_history():
    summary = summarise_financials([])
    assert summary["income_trend"] == "unknown"
    assert summary["hot_prospect"] is False
