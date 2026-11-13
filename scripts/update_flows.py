from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_tracker.config import load_config
from market_tracker.gaps import missing_weekdays
from market_tracker.krx_derivatives import collect_derivatives
from market_tracker.models import DailyMarketData, DerivativeData
from market_tracker.pykrx_collector import PykrxCollector
from market_tracker.storage import read_flows, upsert_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="일일 수급 데이터를 수집합니다.")
    parser.add_argument("--date", help="수집일(YYYY-MM-DD), 기본값은 오늘")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--output", default=str(ROOT / "data" / "flows.csv"))
    parser.add_argument("--no-gap-fill", action="store_true", help="빠진 과거 거래일을 채우지 않음")
    return parser.parse_args()


def collect_missing(config: dict, collector: PykrxCollector, output: str, trading_date: date) -> list[dict]:
    """수집 실패로 빠진 최근 거래일을 다시 수집합니다. 하루가 실패해도 나머지는 계속합니다."""
    lookback = int(config["collector"].get("gap_fill_lookback_days", 45))
    interval = float(config["collector"].get("request_interval_seconds", 0.4))
    existing = read_flows(output)
    candidates = missing_weekdays(existing.get("date", []), trading_date, lookback)
    rows: list[dict] = []
    for missing_date in candidates:
        try:
            spot = collector.collect_spot(missing_date)
        except Exception as exc:
            print(f"{missing_date}: 누락분 현물 수집 실패 ({exc})")
            continue
        if spot is None:
            print(f"{missing_date}: 휴장일 건너뜀")
            continue
        derivatives = DerivativeData(source="unavailable", fallback_used=False)
        try:
            derivatives = collect_derivatives(config, missing_date, allow_naver_fallback=True)
        except Exception as exc:
            print(f"{missing_date}: 누락분 파생 수집 불가 ({exc})")
        flows, close, change_pct, skhynix, samsung = spot
        rows.append(
            DailyMarketData(missing_date, flows, close, change_pct, skhynix, samsung, derivatives).to_row()
        )
        print(f"{missing_date}: 누락분 수집 (파생={derivatives.source})")
        time.sleep(interval)
    return rows


def main() -> int:
    args = parse_args()
    trading_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    config = load_config(args.config)
    spot_collector = PykrxCollector(config)
    market = config["market"]
    pages_path = ROOT / "docs" / "data" / "flows.csv"

    if not args.no_gap_fill:
        missing_rows = collect_missing(config, spot_collector, args.output, trading_date)
        if missing_rows:
            frame = upsert_rows(
                args.output,
                missing_rows,
                float(market["cd_rate"]),
                float(market["dividend_yield"]),
                pages_path,
            )
            print(f"누락분 {len(missing_rows)}개 거래일 반영 (전체 {len(frame)}행)")

    # 휴장일은 pykrx 결과가 비어 있으므로 정상 종료합니다.
    spot = spot_collector.collect_spot(trading_date)
    if spot is None:
        print(f"{trading_date}: 휴장일 또는 데이터 미공개 - 정상 종료")
        return 0

    derivatives = collect_derivatives(config, trading_date, allow_naver_fallback=True)
    flows, close, change_pct, skhynix, samsung = spot

    daily = DailyMarketData(
        trading_date=trading_date,
        flows=flows,
        k200_close=close,
        k200_change_pct=change_pct,
        skhynix_foreign=skhynix,
        samsung_foreign=samsung,
        derivatives=derivatives,
    )
    frame = upsert_rows(
        args.output,
        [daily.to_row()],
        float(market["cd_rate"]),
        float(market["dividend_yield"]),
        pages_path,
    )
    print(f"{trading_date}: 저장 완료 ({len(frame)}행, 파생={derivatives.source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
