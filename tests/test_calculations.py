from datetime import date

import pandas as pd

from market_tracker.calculations import add_derived_fields, basis_badge, nearest_quarterly_expiry, second_thursday


def test_second_thursday_and_nearest_expiry():
    assert second_thursday(2026, 6) == date(2026, 6, 11)
    assert nearest_quarterly_expiry(date(2026, 6, 11)) == date(2026, 6, 11)
    assert nearest_quarterly_expiry(date(2026, 6, 12)) == date(2026, 9, 10)


def test_add_derived_fields_and_rolling_sum():
    frame = pd.DataFrame(
        [
            {"date": "2026-06-10", "k200_close": 400, "futures_close": 403, "foreign": 10, "foreign_futures": 4},
            {"date": "2026-06-11", "k200_close": 402, "futures_close": 401, "foreign": -3, "foreign_futures": 6},
        ]
    )
    result = add_derived_fields(frame, cd_rate=0.03, dividend_yield=0.02)
    assert result.iloc[0]["basis"] == 3
    assert result.iloc[1]["foreign_spot_20d"] == 7
    assert result.iloc[1]["foreign_futures_20d"] == 10
    assert result.iloc[1]["days_to_expiry"] == 0


def test_basis_badge_rules():
    assert basis_badge(-0.1, 1.0) == "🔻백워데이션"
    assert basis_badge(4.1, 2.0) == "⚠️콘탱고 과열"
    assert basis_badge(2.5, 1.0) == "정상권"

