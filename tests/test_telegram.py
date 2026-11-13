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



def test_streak_cumulative_and_missing_futures_flow():
    from market_tracker.telegram import cumulative, streak_text

    frame = pd.DataFrame(
        {
            "date": ["2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20"],
            "foreign": [100, -200, -300, -400],
            "foreign_futures": [0, 0, 0, 0],
            "institution_futures": [0, 0, 0, 0],
            "k200_close": [1000, 1010, 1020, 1030],
        }
    )
    assert streak_text(frame, "foreign") == "3일 연속 순매도"
    assert cumulative(frame, "foreign", 3) == -900
    assert cumulative(frame, "foreign", 5) is None
    message = build_message(frame, "https://example.github.io/flows/")
    assert "투자자 수급: 데이터 확인 필요" in message
    assert "외인: 3일 연속 순매도" in message
