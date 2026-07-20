from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from .calculations import add_derived_fields
from .models import CSV_COLUMNS


def read_flows(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return pd.DataFrame(columns=CSV_COLUMNS)
    return pd.read_csv(csv_path, dtype={"date": str})


def upsert_rows(
    path: str | Path,
    rows: list[dict[str, Any]],
    cd_rate: float,
    dividend_yield: float,
    pages_path: str | Path | None = "docs/data/flows.csv",
) -> pd.DataFrame:
    """같은 날짜를 마지막 값으로 덮어쓰고 전체 파생값을 재계산합니다."""
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    current = read_flows(csv_path)
    incoming = pd.DataFrame(rows)
    combined = pd.concat([current, incoming], ignore_index=True, sort=False)
    if combined.empty:
        combined = pd.DataFrame(columns=CSV_COLUMNS)
    else:
        combined = add_derived_fields(combined, cd_rate, dividend_yield)

    for column in CSV_COLUMNS:
        if column not in combined.columns:
            combined[column] = None
    combined = combined[CSV_COLUMNS]
    combined.to_csv(csv_path, index=False, encoding="utf-8")

    if pages_path:
        public_path = Path(pages_path)
        public_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(csv_path, public_path)
    return combined

