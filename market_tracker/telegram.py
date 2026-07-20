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


def build_message(frame: pd.DataFrame, dashboard_url: str) -> str:
    if frame.empty:
        raise ValueError("텔레그램 메시지를 만들 데이터가 없습니다.")
    ordered = frame.sort_values("date")
    row = ordered.iloc[-1]
    trading_date = datetime.strptime(str(row["date"]), "%Y-%m-%d")
    badge = basis_badge(_number(row.get("basis")), _number(row.get("theoretical_basis")))

    change = _number(row.get("k200_change_pct"))
    change_text = "-" if change is None else f"{change:+.2f}%"
    lines = [
        f"📊 <b>수급 리포트</b> ({trading_date.month}/{trading_date.day} {WEEKDAYS[trading_date.weekday()]})",
        f"K200 {_number(row.get('k200_close')) or 0:,.2f} ({change_text})",
        "",
        "현물(억): "
        f"개인 {format_money(row.get('individual'))} | "
        f"외인 {format_money(row.get('foreign'))} | "
        f"기관 {format_money(row.get('institution'))}",
        "선물(억): "
        f"외인 {format_money(row.get('foreign_futures'))} | "
        f"기관 {format_money(row.get('institution_futures'))}",
        f"금융투자: {format_money(row.get('financial_investment'))}",
        "",
        f"베이시스: {format_point(row.get('basis'))}pt "
        f"(이론 {format_point(row.get('theoretical_basis'))}) {badge}",
        "외인 20일 누적: "
        f"현물 {format_money(row.get('foreign_spot_20d'), '조')} / "
        f"선물 {format_money(row.get('foreign_futures_20d'), '조')}",
        "",
        f"하이닉스 외인: {format_money(row.get('skhynix_foreign'))}억",
        f"삼성전자 외인: {format_money(row.get('samsung_foreign'))}억",
    ]
    if _as_bool(row.get("fallback_used")):
        lines.append("<i>※ 선물 데이터: 네이버 폴백</i>")
    flip = direction_change(ordered)
    if flip:
        lines.extend(["", flip])
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
