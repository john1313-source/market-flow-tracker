from __future__ import annotations

import io
import json
import re
from datetime import date
from typing import Any, Iterable
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .models import DerivativeData


class KrxUnavailable(RuntimeError):
    """KRX OTP/다운로드가 이용 불가할 때 발생합니다."""


def parse_number(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().replace(",", "").replace("+", "")
    if text in {"", "-", "--", "N/A", "nan"}:
        return None
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", "", str(value)).replace("\n", "")


def _matching_column(columns: Iterable[Any], include: tuple[str, ...], exclude: tuple[str, ...] = ()) -> Any | None:
    for column in columns:
        name = _normalized(column)
        if all(token in name for token in include) and not any(token in name for token in exclude):
            return column
    return None


class KrxDerivativesCollector:
    GENERATE_URL = "https://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd"
    DOWNLOAD_URL = "https://data.krx.co.kr/comm/fileDn/download_csv/download.cmd"
    FRONT_REFERER = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201050103"
    INVESTOR_REFERER = "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201050302"

    def __init__(self, config: dict[str, Any], session: requests.Session | None = None):
        self.config = config
        self.collector_config = config.get("collector", {})
        self.timeout = float(self.collector_config.get("request_timeout_seconds", 20))
        self.session = session or self._authenticated_session() or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
            }
        )

    @staticmethod
    def _authenticated_session() -> requests.Session | None:
        """pykrx가 만든 KRX 로그인 쿠키 세션을 OTP 요청에도 재사용합니다."""
        try:
            from pykrx.website.comm.auth import get_auth_session

            auth_session = get_auth_session()
            return None if auth_session is None else auth_session.session
        except ImportError:
            return None

    def _download_csv(self, bld: str, params: dict[str, str], referer: str) -> pd.DataFrame:
        payload = {
            "locale": "ko_KR",
            "csvxls_isNo": "false",
            "name": "fileDown",
            "url": bld,
            **params,
        }
        # KRX는 Referer가 없으면 OTP 요청을 차단하므로 두 요청에 모두 넣습니다.
        response = self.session.post(
            self.GENERATE_URL,
            data=payload,
            headers={"Referer": referer},
            timeout=self.timeout,
        )
        response.raise_for_status()
        otp = response.text.strip()
        if not otp or otp.upper() in {"LOGOUT", "ERROR"} or "<html" in otp.lower():
            raise KrxUnavailable(f"KRX OTP 발급 실패: {otp[:80] or 'empty response'}")

        download = self.session.post(
            self.DOWNLOAD_URL,
            data={"code": otp},
            headers={"Referer": referer},
            timeout=self.timeout,
        )
        download.raise_for_status()
        if b"<html" in download.content[:200].lower():
            raise KrxUnavailable("KRX CSV 대신 오류 페이지를 받았습니다.")

        for encoding in ("euc-kr", "cp949", "utf-8-sig"):
            try:
                text = download.content.decode(encoding)
                return pd.read_csv(io.StringIO(text))
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        raise KrxUnavailable("KRX CSV 인코딩을 해석하지 못했습니다.")

    def _try_blds(self, blds: list[str], params: dict[str, str], referer: str) -> pd.DataFrame:
        errors: list[str] = []
        for bld in blds:
            try:
                frame = self._download_csv(bld, params, referer)
                if not frame.empty:
                    return frame
                errors.append(f"{bld}: empty")
            except (requests.RequestException, KrxUnavailable, ValueError) as exc:
                errors.append(f"{bld}: {exc}")
        raise KrxUnavailable("; ".join(errors))

    def collect(self, trading_date: date) -> DerivativeData:
        query_date = trading_date.strftime("%Y%m%d")
        product_id = str(self.collector_config.get("kospi200_futures_product_id", "KRDRVFUK2I"))
        common = {
            "mktId": "DRV",
            "prodId": product_id,
            "strtDd": query_date,
            "endDd": query_date,
            "trdDd": query_date,
            "inqTpCd": "2",
            "share": "1",
            "money": "1",
        }
        front = self._try_blds(
            list(self.collector_config.get("krx_front_month_blds", [])),
            common,
            self.FRONT_REFERER,
        )
        investor = self._try_blds(
            list(self.collector_config.get("krx_investor_blds", [])),
            common,
            self.INVESTOR_REFERER,
        )
        close, open_interest = self._parse_front_month(front, trading_date)
        foreign, institution = self._parse_investors(investor)
        if close is None or open_interest is None:
            raise KrxUnavailable("KRX 최근월물 CSV에서 종가 또는 미결제약정을 찾지 못했습니다.")
        if foreign is None:
            raise KrxUnavailable("KRX 투자자 CSV에서 외국인 선물 순매수를 찾지 못했습니다.")
        return DerivativeData(
            futures_close=close,
            foreign_futures=foreign,
            institution_futures=institution,
            open_interest=open_interest,
            source="krx",
            fallback_used=False,
        )

    @staticmethod
    def _parse_front_month(frame: pd.DataFrame, trading_date: date) -> tuple[float | None, float | None]:
        date_column = _matching_column(frame.columns, ("일자",)) or _matching_column(frame.columns, ("거래일",))
        selected = frame
        if date_column is not None:
            normalized_date = trading_date.strftime("%Y%m%d")
            mask = frame[date_column].astype(str).str.replace(r"\D", "", regex=True) == normalized_date
            if mask.any():
                selected = frame.loc[mask]
        row = selected.iloc[-1]
        close_column = _matching_column(frame.columns, ("종가",), ("대비",)) or _matching_column(frame.columns, ("정산가",))
        oi_column = _matching_column(frame.columns, ("미결제약정",))
        return (
            parse_number(row.get(close_column)) if close_column is not None else None,
            parse_number(row.get(oi_column)) if oi_column is not None else None,
        )

    @staticmethod
    def _parse_investors(frame: pd.DataFrame) -> tuple[float | None, float | None]:
        investor_column = _matching_column(frame.columns, ("투자자",)) or frame.columns[0]
        net_value_column = (
            _matching_column(frame.columns, ("순매수", "거래대금"))
            or _matching_column(frame.columns, ("순매수", "금액"))
            or _matching_column(frame.columns, ("순매수",))
        )
        if net_value_column is None:
            buy_column = _matching_column(frame.columns, ("매수", "거래대금"))
            sell_column = _matching_column(frame.columns, ("매도", "거래대금"))
            if buy_column is None or sell_column is None:
                return None, None
            values = frame[buy_column].map(parse_number).fillna(0) - frame[sell_column].map(parse_number).fillna(0)
        else:
            values = frame[net_value_column].map(parse_number)

        names = frame[investor_column].map(_normalized)

        def value_for(tokens: tuple[str, ...]) -> float | None:
            mask = names.map(lambda name: any(token in name for token in tokens))
            matched = pd.to_numeric(values[mask], errors="coerce").dropna()
            return None if matched.empty else float(matched.iloc[0])

        # KRX 거래대금 CSV가 백만원 단위이면 헤더에 표시된 단위를 원으로 환산합니다.
        header_text = " ".join(map(str, frame.columns))
        multiplier = 1_000_000 if "백만원" in header_text else 1.0
        foreign = value_for(("외국인",))
        institution = value_for(("기관합계", "기관계"))
        if institution is None:
            institution_tokens = ("금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금")
            mask = names.map(lambda name: any(token in name for token in institution_tokens))
            detailed = pd.to_numeric(values[mask], errors="coerce").dropna()
            if not detailed.empty:
                institution = float(detailed.sum())
        return (
            None if foreign is None else foreign * multiplier,
            None if institution is None else institution * multiplier,
        )


class NaverFuturesFallback:
    def __init__(self, config: dict[str, Any], session: requests.Session | None = None):
        self.collector_config = config.get("collector", {})
        self.timeout = float(self.collector_config.get("request_timeout_seconds", 20))
        self.base_url = str(
            self.collector_config.get(
                "naver_futures_url",
                "https://m.stock.naver.com/domestic/index/FUT/total",
            )
        )
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"})

    def collect(self, trading_date: date) -> DerivativeData:
        response = self.session.get(self.base_url, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, "lxml")

        # 현재 Npay 증권은 Next.js 구조화 JSON에 최근월물과 투자자 수급을 넣습니다.
        mobile_data = self._parse_mobile_page(soup, trading_date)
        if mobile_data is not None:
            return mobile_data

        day_url = self._find_front_month_url(soup)
        pages = [response.text]
        if day_url:
            day_response = self.session.get(urljoin(self.base_url, day_url), timeout=self.timeout)
            day_response.raise_for_status()
            day_response.encoding = day_response.apparent_encoding or "euc-kr"
            pages.insert(0, day_response.text)

        close = open_interest = None
        foreign = institution = None
        for html in pages:
            tables = pd.read_html(io.StringIO(html))
            if close is None:
                close, open_interest = self._parse_price_tables(tables, trading_date)
            if foreign is None:
                foreign, institution = self._parse_investor_tables(tables)
        if close is None:
            raise KrxUnavailable("네이버 선물 페이지에서도 최근월물 종가를 찾지 못했습니다.")
        return DerivativeData(
            futures_close=close,
            foreign_futures=foreign,
            institution_futures=institution,
            open_interest=open_interest,
            source="naver",
            fallback_used=True,
        )

    @staticmethod
    def _walk_json(value: Any):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from NaverFuturesFallback._walk_json(child)
        elif isinstance(value, list):
            for child in value:
                yield from NaverFuturesFallback._walk_json(child)

    @staticmethod
    def _parse_mobile_page(soup: BeautifulSoup, trading_date: date) -> DerivativeData | None:
        script = soup.find("script", id="__NEXT_DATA__")
        if script is None or not script.string:
            return None
        try:
            payload = json.loads(script.string)
        except json.JSONDecodeError:
            return None

        quote: dict[str, Any] | None = None
        trend: dict[str, Any] | None = None
        for item in NaverFuturesFallback._walk_json(payload):
            if quote is None and item.get("itemCode") == "FUT" and "closePrice" in item:
                quote = item
            if trend is None and isinstance(item.get("dealTrendInfo"), dict):
                trend = item["dealTrendInfo"]

        if quote is None:
            return None
        query_date = trading_date.strftime("%Y%m%d")
        traded_at = re.sub(r"\D", "", str(quote.get("localTradedAt", "")))[:8]
        trend_date = re.sub(r"\D", "", str((trend or {}).get("bizdate", "")))[:8]
        # 모바일 페이지는 최신 일자만 제공하므로 과거 백필에 현재 값을 섞지 않습니다.
        available_dates = {value for value in (traded_at, trend_date) if value}
        if available_dates and query_date not in available_dates:
            raise KrxUnavailable(f"네이버 모바일 선물 페이지에 {trading_date} 과거 데이터가 없습니다.")

        close = parse_number(quote.get("closePrice"))
        if close is None:
            return None
        # Npay 화면의 투자자 동향 표시 단위는 억원입니다.
        foreign = parse_number((trend or {}).get("foreignValue"))
        institution = parse_number((trend or {}).get("institutionalValue"))
        return DerivativeData(
            futures_close=close,
            foreign_futures=None if foreign is None else foreign * 100_000_000,
            institution_futures=None if institution is None else institution * 100_000_000,
            open_interest=None,
            source="naver",
            fallback_used=True,
        )

    @staticmethod
    def _find_front_month_url(soup: BeautifulSoup) -> str | None:
        candidates = []
        for link in soup.select('a[href*="sise_future_day.naver"]'):
            label = _normalized(link.get_text(" ", strip=True))
            href = link.get("href")
            if href:
                candidates.append((0 if "KOSPI200" in label or "코스피200" in label else 1, href))
        return sorted(candidates)[0][1] if candidates else None

    @staticmethod
    def _parse_price_tables(tables: list[pd.DataFrame], trading_date: date) -> tuple[float | None, float | None]:
        date_texts = {trading_date.strftime("%Y.%m.%d"), trading_date.strftime("%Y-%m-%d"), trading_date.strftime("%m.%d")}
        for table in tables:
            flat_columns = [_normalized(value) for value in table.columns]
            close_idx = next((index for index, value in enumerate(flat_columns) if "종가" in value), None)
            if close_idx is None:
                continue
            oi_idx = next((index for index, value in enumerate(flat_columns) if "미결제" in value), None)
            for _, row in table.iterrows():
                row_text = " ".join(map(str, row.tolist()))
                if any(text in row_text for text in date_texts):
                    return parse_number(row.iloc[close_idx]), parse_number(row.iloc[oi_idx]) if oi_idx is not None else None
            # 당일 표처럼 날짜가 생략된 경우 첫 유효 종가를 사용합니다.
            values = table.iloc[:, close_idx].map(parse_number).dropna()
            if not values.empty:
                return float(values.iloc[0]), None
        return None, None

    @staticmethod
    def _parse_investor_tables(tables: list[pd.DataFrame]) -> tuple[float | None, float | None]:
        for table in tables:
            text = table.astype(str).apply(lambda row: " ".join(row), axis=1)
            if not text.str.contains("외국인").any():
                continue
            numbers: dict[str, float] = {}
            for row_text in text:
                for name in ("외국인", "기관계", "기관"):
                    if name in row_text:
                        matches = re.findall(r"[+\-]?\d[\d,]*(?:\.\d+)?", row_text)
                        if matches:
                            numbers[name] = parse_number(matches[-1]) or 0.0
            return numbers.get("외국인"), numbers.get("기관계", numbers.get("기관"))
        return None, None


def collect_derivatives(config: dict[str, Any], trading_date: date, allow_naver_fallback: bool = True) -> DerivativeData:
    try:
        return KrxDerivativesCollector(config).collect(trading_date)
    except (KrxUnavailable, requests.RequestException, ValueError):
        if not allow_naver_fallback:
            raise
        return NaverFuturesFallback(config).collect(trading_date)
