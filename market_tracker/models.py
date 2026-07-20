from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


CSV_COLUMNS = [
    "date",
    "financial_investment",
    "insurance",
    "investment_trust",
    "private_equity",
    "bank",
    "other_finance",
    "pension",
    "individual",
    "foreign",
    "institution",
    "k200_close",
    "k200_change_pct",
    "skhynix_foreign",
    "samsung_foreign",
    "futures_close",
    "foreign_futures",
    "institution_futures",
    "open_interest",
    "expiry_date",
    "days_to_expiry",
    "basis",
    "theoretical_basis",
    "basis_gap",
    "basis_gap_pct",
    "foreign_spot_20d",
    "foreign_futures_20d",
    "derivative_source",
    "fallback_used",
]


@dataclass(slots=True)
class DerivativeData:
    futures_close: float | None = None
    foreign_futures: float | None = None
    institution_futures: float | None = None
    open_interest: float | None = None
    source: str = "krx"
    fallback_used: bool = False


@dataclass(slots=True)
class DailyMarketData:
    trading_date: date
    flows: dict[str, float]
    k200_close: float
    k200_change_pct: float | None
    skhynix_foreign: float | None
    samsung_foreign: float | None
    derivatives: DerivativeData

    def to_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {"date": self.trading_date.isoformat()}
        row.update(self.flows)
        row.update(
            {
                "k200_close": self.k200_close,
                "k200_change_pct": self.k200_change_pct,
                "skhynix_foreign": self.skhynix_foreign,
                "samsung_foreign": self.samsung_foreign,
                "futures_close": self.derivatives.futures_close,
                "foreign_futures": self.derivatives.foreign_futures,
                "institution_futures": self.derivatives.institution_futures,
                "open_interest": self.derivatives.open_interest,
                "derivative_source": self.derivatives.source,
                "fallback_used": self.derivatives.fallback_used,
            }
        )
        return row

