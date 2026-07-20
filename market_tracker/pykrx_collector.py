from __future__ import annotations

from datetime import date, timedelta
import os
from typing import Any

import pandas as pd

from .models import DailyMarketData, DerivativeData


FLOW_COLUMN_MAP = {
    "금융투자": "financial_investment",
    "보험": "insurance",
    "투신": "investment_trust",
    "사모": "private_equity",
    "은행": "bank",
    "기타금융": "other_finance",
    "연기금": "pension",
    "연기금등": "pension",
    "개인": "individual",
    "외국인": "foreign",
    "외국인합계": "foreign",
}

INSTITUTION_COLUMNS = [
    "financial_investment",
    "insurance",
    "investment_trust",
    "private_equity",
    "bank",
    "other_finance",
    "pension",
]


def _last_value(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    value = pd.to_numeric(frame[column], errors="coerce").dropna()
    return None if value.empty else float(value.iloc[-1])


class PykrxCollector:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        require_credentials = bool(config.get("collector", {}).get("require_krx_credentials", True))
        if require_credentials and not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
            raise RuntimeError(
                "KRX_ID와 KRX_PW 환경변수가 필요합니다. 누락을 휴장일로 오인하지 않도록 수집을 중단합니다."
            )

        # 자격 증명을 확인한 뒤 가져와야 pykrx가 인증 세션을 정상 초기화합니다.
        from pykrx import stock
        from pykrx.website.comm.auth import get_auth_session

        self.stock = stock
        if require_credentials and get_auth_session() is None:
            raise RuntimeError("KRX 로그인에 실패했습니다. KRX_ID/KRX_PW를 확인하세요.")

    def is_trading_day(self, trading_date: date) -> bool:
        value = trading_date.strftime("%Y%m%d")
        frame = self.stock.get_market_trading_value_by_date(value, value, "KOSPI", detail=True)
        return not frame.empty

    def collect_spot(self, trading_date: date) -> tuple[dict[str, float], float, float | None, float | None, float | None] | None:
        query_date = trading_date.strftime("%Y%m%d")
        raw_flows = self.stock.get_market_trading_value_by_date(
            query_date,
            query_date,
            "KOSPI",
            detail=True,
        )
        if raw_flows.empty:
            return None

        last = raw_flows.iloc[-1]
        flows: dict[str, float] = {name: 0.0 for name in FLOW_COLUMN_MAP.values()}
        for korean_name, english_name in FLOW_COLUMN_MAP.items():
            if korean_name in last.index:
                flows[english_name] = float(last[korean_name])
        flows["institution"] = sum(flows.get(name, 0.0) for name in INSTITUTION_COLUMNS)

        # 전일 등락률을 정확히 구하기 위해 달력일 기준 10일을 함께 조회합니다.
        start = (trading_date - timedelta(days=10)).strftime("%Y%m%d")
        index_ticker = str(self.config["collector"].get("kospi200_index_ticker", "1028"))
        index_frame = self.stock.get_index_ohlcv_by_date(start, query_date, index_ticker)
        if index_frame.empty:
            raise RuntimeError(f"{trading_date}: 코스피200 지수 데이터가 비어 있습니다.")
        closes = pd.to_numeric(index_frame["종가"], errors="coerce").dropna()
        k200_close = float(closes.iloc[-1])
        k200_change_pct = None
        if len(closes) >= 2 and closes.iloc[-2] != 0:
            k200_change_pct = float((closes.iloc[-1] / closes.iloc[-2] - 1) * 100)

        skhynix = self._stock_foreign(query_date, "000660")
        samsung = self._stock_foreign(query_date, "005930")
        return flows, k200_close, k200_change_pct, skhynix, samsung

    def _stock_foreign(self, query_date: str, ticker: str) -> float | None:
        frame = self.stock.get_market_trading_value_by_date(query_date, query_date, ticker)
        for column in ("외국인", "외국인합계"):
            value = _last_value(frame, column)
            if value is not None:
                return value
        return None

    def build_daily(
        self,
        trading_date: date,
        derivatives: DerivativeData,
    ) -> DailyMarketData | None:
        spot = self.collect_spot(trading_date)
        if spot is None:
            return None
        flows, close, change_pct, skhynix, samsung = spot
        return DailyMarketData(
            trading_date=trading_date,
            flows=flows,
            k200_close=close,
            k200_change_pct=change_pct,
            skhynix_foreign=skhynix,
            samsung_foreign=samsung,
            derivatives=derivatives,
        )
