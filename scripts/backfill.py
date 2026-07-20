from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_tracker.config import load_config
from market_tracker.krx_derivatives import collect_derivatives
from market_tracker.models import DailyMarketData, DerivativeData
from market_tracker.pykrx_collector import PykrxCollector
from market_tracker.storage import upsert_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="과거 수급 데이터를 백필합니다.")
    parser.add_argument("--start", default="2026-05-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--output", default=str(ROOT / "data" / "flows.csv"))
    parser.add_argument("--skip-derivatives", action="store_true", help="pykrx 현물 데이터만 백필")
    return parser.parse_args()


def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def main() -> int:
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    if end < start:
        raise ValueError("--end는 --start 이후여야 합니다.")

    config = load_config(args.config)
    collector = PykrxCollector(config)
    interval = float(config["collector"].get("request_interval_seconds", 0.4))
    rows = []
    for trading_date in date_range(start, end):
        if trading_date.weekday() >= 5:
            continue
        spot = collector.collect_spot(trading_date)
        if spot is None:
            print(f"{trading_date}: 휴장일 건너뜀")
            continue
        derivatives = DerivativeData(source="unavailable", fallback_used=False)
        if not args.skip_derivatives:
            try:
                derivatives = collect_derivatives(config, trading_date, allow_naver_fallback=True)
            except Exception as exc:
                # 백필은 가능한 날짜를 최대한 보존하되 실패 사실을 행에 남깁니다.
                print(f"{trading_date}: 파생 백필 불가 ({exc})")
        flows, close, change_pct, skhynix, samsung = spot
        rows.append(
            DailyMarketData(
                trading_date,
                flows,
                close,
                change_pct,
                skhynix,
                samsung,
                derivatives,
            ).to_row()
        )
        time.sleep(interval)

    market = config["market"]
    frame = upsert_rows(
        args.output,
        rows,
        float(market["cd_rate"]),
        float(market["dividend_yield"]),
        ROOT / "docs" / "data" / "flows.csv",
    )
    print(f"백필 완료: {len(rows)}개 거래일 반영, 전체 {len(frame)}행")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

