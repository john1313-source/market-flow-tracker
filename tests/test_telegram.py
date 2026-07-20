import pandas as pd

from market_tracker.telegram import build_message, direction_change


def sample_frame():
    return pd.DataFrame(
        [
            {"date": "2026-07-17", "foreign": -1},
            {
                "date": "2026-07-20",
                "foreign": 223_700_000_000,
                "individual": -89_000_000_000,
                "institution": -160_200_000_000,
                "financial_investment": -120_300_000_000,
                "foreign_futures": 18_100_000_000,
                "institution_futures": 58_300_000_000,
                "k200_close": 1034.83,
                "k200_change_pct": -4.21,
                "basis": 6.6,
                "theoretical_basis": 3.5,
                "foreign_spot_20d": -8_200_000_000_000,
                "foreign_futures_20d": 1_100_000_000_000,
                "skhynix_foreign": -124_000_000_000,
                "samsung_foreign": -89_000_000_000,
                "fallback_used": False,
            },
        ]
    )


def test_direction_change_and_message():
    frame = sample_frame()
    assert direction_change(frame) == "↩️ 외인 현물 매도→매수 전환"
    message = build_message(frame, "https://example.github.io/flows/")
    assert "⚠️콘탱고 과열" in message
    assert "외인 +2,237" in message
    assert 'parse_mode' not in message
    assert '<a href="https://example.github.io/flows/">대시보드</a>' in message

