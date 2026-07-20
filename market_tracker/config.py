from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    config.setdefault("market", {})
    config.setdefault("collector", {})
    config.setdefault("telegram", {})

    # Actions나 로컬 환경변수로 공개 대시보드 주소를 쉽게 바꿀 수 있게 합니다.
    dashboard_url = os.getenv("DASHBOARD_URL")
    if dashboard_url:
        config["telegram"]["dashboard_url"] = dashboard_url
    return config

