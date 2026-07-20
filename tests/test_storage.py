import pandas as pd

from market_tracker.storage import upsert_rows


def test_upsert_is_idempotent(tmp_path):
    output = tmp_path / "data" / "flows.csv"
    public = tmp_path / "docs" / "data" / "flows.csv"
    first = {
        "date": "2026-07-20",
        "foreign": 100,
        "foreign_futures": 20,
        "k200_close": 400,
        "futures_close": 402,
    }
    second = {**first, "foreign": 250}
    upsert_rows(output, [first], 0.03, 0.02, public)
    result = upsert_rows(output, [second], 0.03, 0.02, public)

    assert len(result) == 1
    assert result.iloc[0]["foreign"] == 250
    assert pd.read_csv(public).iloc[0]["foreign"] == 250

