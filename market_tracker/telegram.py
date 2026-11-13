from __future__ import annotations

import html
import os
from datetime import datetime
from typing import Any

import pandas as pd
import requests

from .calculations import basis_badge


WEEKDAYS = "월화수목금토일"


def _number(value: Any) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def _as_bool(value: Any) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def format_money(value: Any, unit: str = "억") -> str:
    number = _number(value)
    if number is None:
        return "-"
    divisor = 100_000_000 if unit == "억" else 1_000_000_000_000
    converted = number / divisor
    if unit == "조":
        return f"{converted:+.1f}조"
    return f"{converted:+,.0f}"


def format_point(value: Any, digits: int = 1) -> str:
    number = _number(value)
    return "-" if number is None else f"{number:+.{digits}f}"


def direction_change(frame: pd.DataFrame) -> str | None:
    values = pd.to_numeric(frame.get("foreign"), errors="coerce").dropna()
    if len(values) < 2 or values.iloc[-1] == 0 or values.iloc[-2] == 0:
        return None
    before, today = values.iloc[-2], values.iloc[-1]
    if before < 0 < today:
        return "↩️ 외인 현물 매도→매수 전환"
    if before > 0 > today:
        return "↩️ 외인 현물 매수→매도 전환"
    return None


INSTITUTION_DETAIL = [
    ("금융투자", "financial_investment"),
    ("연기금", "pension"),
    ("투신", "investment_trust"),
    ("사모", "private_equity"),
    ("보험", "insurance"),
    ("은행", "bank"),
    ("기타금융", "other_finance"),
]


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def streak_text(frame: pd.DataFrame, column: str) -> str | None:
    """마지막 날과 같은 방향이 며칠째 이어지는지 반환합니다."""
    values = _series(frame, column).dropna()
    if values.empty or values.iloc[-1] == 0:
        return None
    positive = values.iloc[-1] > 0
    count = 0
    for value in reversed(values.tolist()):
        if value == 0 or (value > 0) != positive:
            break
        count += 1
    return f"{count}일 연속 {'순매수' if positive else '순매도'}"


def cumulative(frame: pd.DataFrame, column: str, days: int) -> float | None:
    values = _series(frame, column).dropna()
    return None if len(values) < days else float(values.iloc[-days:].sum())


def period_return(frame: pd.DataFrame, days: int) -> float | None:
    closes = _series(frame, "k200_close").dropna()
    if len(closes) <= days or closes.iloc[-days - 1] == 0:
        return None
    return float((closes.iloc[-1] / closes.iloc[-days - 1] - 1) * 100)


def extreme_text(frame: pd.DataFrame, column: str, label: str, window: int = 20) -> str | None:
    """오늘 값이 최근 window거래일 중 가장 큰 순매수/순매도이면 알려 줍니다."""
    values = _series(frame, column).dropna()
    if len(values) < window:
        return None
    recent = values.iloc[-window:]
    today = recent.iloc[-1]
    if today < 0 and today == recent.min():
        return f"{label} 순매도 최근 {window}거래일 중 최대"
    if today > 0 and today == recent.max():
        return f"{label} 순매수 최근 {window}거래일 중 최대"
    return None


def flow_summary(frame: pd.DataFrame, column: str, label: str) -> str | None:
    parts = [text for text in (streak_text(frame, column),) if text]
    five = cumulative(frame, column, 5)
    if five is not None:
        parts.append(f"5일 {format_money(five, '조')}")
    twenty = cumulative(frame, column, 20)
    if twenty is not None:
        parts.append(f"20일 {format_money(twenty, '조')}")
    return f"{label}: " + " · ".join(parts) if parts else None


def futures_flow_missing(row: pd.Series) -> bool:
    """외국인·기관 선물 순매수가 둘 다 비었거나 0이면 수집값을 믿을 수 없다고 봅니다."""
    foreign = _number(row.get("foreign_futures"))
    institution = _number(row.get("institution_futures"))
    return not foreign and not institution


def signals(frame: pd.DataFrame) -> list[str]:
    result: list[str] = []
    flip = direction_change(frame)
    if flip:
        result.append(flip)
    for column, label in (("foreign", "외인 현물"), ("institution", "기관 현물")):
        text = extreme_text(frame, column, label)
        if text:
            result.append(f"📌 {text}")
    if len(frame) >= 2:
        today, before = frame.iloc[-1], frame.iloc[-2]
        badge_today = basis_badge(_number(today.get("basis")), _number(today.get("theoretical_basis")))
        badge_before = basis_badge(_number(before.get("basis")), _number(before.get("theoretical_basis")))
        if badge_today != badge_before and "확인" not in badge_today + badge_before:
            result.append(f"🔄 베이시스 {badge_before} → {badge_today}")
    row = frame.iloc[-1]
    foreign_spot = _number(row.get("foreign"))
    foreign_futures = _number(row.get("foreign_futures"))
    if not futures_flow_missing(row) and foreign_spot and foreign_futures:
        if foreign_spot > 0 and foreign_futures > 0:
            result.append("🟢 외인 현물·선물 동반 순매수")
        elif foreign_spot < 0 and foreign_futures < 0:
            result.append("🔴 외인 현물·선물 동반 순매도")
    return result


def build_message(frame: pd.DataFrame, dashboard_url: str) -> str:
    if frame.empty:
        raise ValueError("텔레그램 메시지를 만들 데이터가 없습니다.")
    ordered = frame.sort_values("date").reset_index(drop=True)
    row = ordered.iloc[-1]
    previous = ordered.iloc[-2] if len(ordered) >= 2 else None
    trading_date = datetime.strptime(str(row["date"]), "%Y-%m-%d")
    badge = basis_badge(_number(row.get("basis")), _number(row.get("theoretical_basis")))

    change = _number(row.get("k200_change_pct"))
    change_text = "-" if change is None else f"{change:+.2f}%"
    lines = [
        f"📊 <b>수급 리포트</b> ({trading_date.month}/{trading_date.day} {WEEKDAYS[trading_date.weekday()]})",
        f"K200 {_number(row.get('k200_close')) or 0:,.2f} ({change_text})",
    ]
    returns = [
        f"{days}일 {value:+.2f}%"
        for days, value in ((days, period_return(ordered, days)) for days in (5, 20))
        if value is not None
    ]
    if returns:
        lines.append("누적 등락: " + " · ".join(returns))

    lines.extend(
        [
            "",
            "<b>현물 (억)</b>",
            f"개인 {format_money(row.get('individual'))} | "
            f"외인 {format_money(row.get('foreign'))} | "
            f"기관 {format_money(row.get('institution'))}",
        ]
    )
    for column, label in (("foreign", "외인"), ("institution", "기관"), ("individual", "개인")):
        summary = flow_summary(ordered, column, label)
        if summary:
            lines.append(summary)

    detail = [
        f"{label} {format_money(row.get(column))}"
        for label, column in INSTITUTION_DETAIL
        if _number(row.get(column)) is not None
    ]
    if detail:
        lines.extend(["", "<b>기관 세부 (억)</b>", " | ".join(detail[:3])])
        if detail[3:]:
            lines.append(" | ".join(detail[3:]))

    lines.extend(["", "<b>선물</b>"])
    futures_close = _number(row.get("futures_close"))
    open_interest = _number(row.get("open_interest"))
    futures_parts = []
    if futures_close is not None:
        futures_parts.append(f"종가 {futures_close:,.2f}")
    if open_interest:
        text = f"미결제 {open_interest:,.0f}"
        before_interest = None if previous is None else _number(previous.get("open_interest"))
        if before_interest:
            text += f" (전 거래일 대비 {open_interest - before_interest:+,.0f})"
        futures_parts.append(text)
    if futures_parts:
        lines.append(" · ".join(futures_parts))
    if futures_flow_missing(row):
        lines.append("투자자 수급: 데이터 확인 필요")
    else:
        lines.append(
            "수급(억): "
            f"외인 {format_money(row.get('foreign_futures'))} | "
            f"기관 {format_money(row.get('institution_futures'))}"
        )
        lines.append(f"외인 20일 누적: {format_money(row.get('foreign_futures_20d'), '조')}")

    lines.extend(
        [
            "",
            "<b>베이시스</b>",
            f"베이시스: {format_point(row.get('basis'))}pt "
            f"(이론 {format_point(row.get('theoretical_basis'))}) {badge}",
        ]
    )
    gap = _number(row.get("basis_gap"))
    gap_pct = _number(row.get("basis_gap_pct"))
    if gap is not None and gap_pct is not None:
        lines.append(f"괴리: {gap:+.2f}pt ({gap_pct:+.2f}%)")
    expiry = str(row.get("expiry_date") or "")
    days_left = _number(row.get("days_to_expiry"))
    if len(expiry) >= 10 and days_left is not None:
        lines.append(f"만기: {int(expiry[5:7])}/{int(expiry[8:10])} (D-{int(days_left)})")

    lines.extend(["", "<b>대형주 외인 (억)</b>"])
    for label, column in (("하이닉스", "skhynix_foreign"), ("삼성전자", "samsung_foreign")):
        text = f"{label}: {format_money(row.get(column))}"
        extras = [value for value in (streak_text(ordered, column),) if value]
        five = cumulative(ordered, column, 5)
        if five is not None:
            extras.append(f"5일 {format_money(five, '조')}")
        if extras:
            text += f" ({' · '.join(extras)})"
        lines.append(text)

    if _as_bool(row.get("fallback_used")):
        lines.append("<i>※ 선물 데이터: 네이버 폴백</i>")
    notes = signals(ordered)
    if notes:
        lines.extend(["", "<b>신호</b>", *notes])
    if previous is not None:
        gap_days = (trading_date - datetime.strptime(str(previous["date"]), "%Y-%m-%d")).days
        if gap_days > 7:
            lines.extend(
                ["", f"<i>※ 직전 데이터가 {gap_days}일 전입니다. 연속·누적·전일 대비 값은 빠진 구간을 건너뛴 값입니다.</i>"]
            )
    safe_url = html.escape(dashboard_url, quote=True)
    lines.extend(["", f'📈 <a href="{safe_url}">대시보드</a>'])
    return "\n".join(lines)


def send_message(message: str, token: str | None = None, chat_id: str | None = None, timeout: float = 15) -> None:
    bot_token = token or os.getenv("BOT_TOKEN")
    target_chat = chat_id or os.getenv("CHAT_ID")
    if not bot_token or not target_chat:
        raise RuntimeError("BOT_TOKEN 또는 CHAT_ID 환경변수가 없습니다.")
    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data={
            "chat_id": target_chat,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"텔레그램 API 오류: {payload}")
