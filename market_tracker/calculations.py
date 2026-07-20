from __future__ import annotations

import calendar
from datetime import date
from typing import Any

import pandas as pd


def second_thursday(year: int, month: int) -> date:
    """주어진 월의 둘째 목요일을 반환합니다."""
    month_calendar = calendar.monthcalendar(year, month)
    thursdays = [week[calendar.THURSDAY] for week in month_calendar if week[calendar.THURSDAY]]
    return date(year, month, thursdays[1])


def nearest_quarterly_expiry(trading_date: date) -> date:
    """거래일 기준 최근월물의 분기 만기일을 계산합니다."""
    for month in (3, 6, 9, 12):
        expiry = second_thursday(trading_date.year, month)
        if trading_date <= expiry:
            return expiry
    return second_thursday(trading_date.year + 1, 3)


def basis_badge(basis: float | None, theoretical_basis: float | None) -> str:
    if basis is None or pd.isna(basis):
        return "데이터 확인 필요"
    if basis < 0:
        return "🔻백워데이션"
    if theoretical_basis is not None and not pd.isna(theoretical_basis) and basis - theoretical_basis >= 2:
        return "⚠️콘탱고 과열"
    return "정상권"


def add_derived_fields(frame: pd.DataFrame, cd_rate: float, dividend_yield: float) -> pd.DataFrame:
    """베이시스와 20일 누적값을 날짜순으로 다시 계산합니다."""
    if frame.empty:
        return frame

    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"])
    result = result.sort_values("date").drop_duplicates("date", keep="last")

    for column in ("k200_close", "futures_close", "foreign", "foreign_futures"):
        result[column] = pd.to_numeric(result.get(column), errors="coerce")

    expiries = [nearest_quarterly_expiry(value.date()) for value in result["date"]]
    result["expiry_date"] = [value.isoformat() for value in expiries]
    result["days_to_expiry"] = [max((expiry - day.date()).days, 0) for expiry, day in zip(expiries, result["date"])]
    result["basis"] = result["futures_close"] - result["k200_close"]
    result["theoretical_basis"] = (
        result["k200_close"]
        * (float(cd_rate) - float(dividend_yield))
        * result["days_to_expiry"]
        / 365
    )
    result["basis_gap"] = result["basis"] - result["theoretical_basis"]
    result["basis_gap_pct"] = result["basis_gap"] / result["k200_close"] * 100
    result["foreign_spot_20d"] = result["foreign"].rolling(20, min_periods=1).sum()
    result["foreign_futures_20d"] = result["foreign_futures"].rolling(20, min_periods=1).sum()
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")
    return result


def clean_row(row: dict[str, Any]) -> dict[str, Any]:
    """CSV에 쓰기 적합하도록 NaN을 빈 값으로 바꿉니다."""
    return {key: (None if pd.isna(value) else value) for key, value in row.items()}

