from datetime import date

from market_tracker.gaps import missing_weekdays


def test_missing_weekdays_skips_weekends_known_dates_and_end():
    existing = ["2026-11-09", "2026-11-11"]
    result = missing_weekdays(existing, date(2026, 11, 13), 7)
    # 11/6(금)~11/12(목) 중 주말(7, 8)과 이미 있는 9, 11을 제외합니다. 13일 당일은 포함하지 않습니다.
    assert result == [date(2026, 11, 6), date(2026, 11, 10), date(2026, 11, 12)]


def test_missing_weekdays_disabled():
    assert missing_weekdays([], date(2026, 11, 13), 0) == []
