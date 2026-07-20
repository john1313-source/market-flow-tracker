from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_tracker.config import load_config
from market_tracker.krx_derivatives import collect_derivatives
from market_tracker.pykrx_collector import PykrxCollector
from market_tracker.storage import upsert_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="일일 수급 데이터를 수집합니다.")
    parser.add_argument("--date", help="수집일(YYYY-MM-DD), 기본값은 오늘")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--output", default=str(ROOT / "data" / "flows.csv"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trading_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    config = load_config(args.config)
    spot_collector = PykrxCollector(config)

    # 휴장일은 pykrx 결과가 비어 있으므로 정상 종료합니다.
    spot = spot_collector.collect_spot(trading_date)
    if spot is None:
        print(f"{trading_date}: 휴장일 또는 데이터 미공개 - 정상 종료")
        return 0

    derivatives = collect_derivatives(config, trading_date, allow_naver_fallback=True)
    flows, close, change_pct, skhynix, samsung = spot
    from market_tracker.models import DailyMarketData

    daily = DailyMarketData(
        trading_date=trading_date,
        flows=flows,
        k200_close=close,
        k200_change_pct=change_pct,
        skhynix_foreign=skhynix,
        samsung_foreign=samsung,
        derivatives=derivatives,
    )
    market = config["market"]
    frame = upsert_rows(
        args.output,
        [daily.to_row()],
        float(market["cd_rate"]),
        float(market["dividend_yield"]),
        ROOT / "docs" / "data" / "flows.csv",
    )
    print(f"{trading_date}: 저장 완료 ({len(frame)}행, 파생={derivatives.source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

