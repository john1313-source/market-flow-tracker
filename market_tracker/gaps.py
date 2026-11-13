from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable


def missing_weekdays(existing_dates: Iterable[str], end: date, lookback_days: int) -> list[date]:
    """end 이전 lookback_days일 안에서 CSV에 없는 평일을 날짜순으로 반환합니다.

    end 당일은 포함하지 않습니다. 휴장일도 평일이면 후보에 들어가므로,
    호출하는 쪽에서 수집 결과가 비어 있으면 건너뛰어야 합니다.
    """
    if lookback_days <= 0:
        return []
    known = {str(value)[:10] for value in existing_dates}
    result: list[date] = []
    current = end - timedelta(days=lookback_days)
    while current < end:
        if current.weekday() < 5 and current.isoformat() not in known:
            result.append(current)
        current += timedelta(days=1)
    return result
