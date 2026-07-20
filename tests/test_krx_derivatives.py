import pandas as pd

from datetime import date

from bs4 import BeautifulSoup

from market_tracker.krx_derivatives import KrxDerivativesCollector, NaverFuturesFallback


def test_parse_front_month_korean_csv_columns():
    frame = pd.DataFrame(
        [
            {
                "일자": "2026/07/20",
                "종가": "1,041.40",
                "미결제약정수량": "333,028",
            }
        ]
    )
    close, open_interest = KrxDerivativesCollector._parse_front_month(
        frame,
        pd.Timestamp("2026-07-20").date(),
    )
    assert close == 1041.4
    assert open_interest == 333028


def test_parse_investors_converts_million_krw():
    frame = pd.DataFrame(
        {
            "투자자구분": ["외국인", "기관계"],
            "순매수 거래대금(백만원)": ["18,100", "58,300"],
        }
    )
    foreign, institution = KrxDerivativesCollector._parse_investors(frame)
    assert foreign == 18_100_000_000
    assert institution == 58_300_000_000


def test_parse_naver_mobile_next_data():
    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"quote":{"itemCode":"FUT","closePrice":"1,039.70",
    "localTradedAt":"2026-07-20T15:06:59+09:00"},
    "detail":{"dealTrendInfo":{"bizdate":"20260720","foreignValue":"+379",
    "institutionalValue":"+1,498"}}}}
    </script>
    """
    result = NaverFuturesFallback._parse_mobile_page(
        BeautifulSoup(html, "lxml"),
        date(2026, 7, 20),
    )
    assert result is not None
    assert result.futures_close == 1039.7
    assert result.foreign_futures == 37_900_000_000
    assert result.institution_futures == 149_800_000_000
    assert result.open_interest is None
    assert result.fallback_used is True
