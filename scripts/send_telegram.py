from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_tracker.config import load_config
from market_tracker.storage import read_flows
from market_tracker.telegram import build_message, send_message


def main() -> int:
    parser = argparse.ArgumentParser(description="최신 수급 리포트를 텔레그램으로 보냅니다.")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--input", default=str(ROOT / "data" / "flows.csv"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    frame = read_flows(args.input)
    message = build_message(frame, str(config["telegram"]["dashboard_url"]))
    if args.dry_run:
        print(message)
        return 0
    send_message(message)
    print("텔레그램 전송 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

