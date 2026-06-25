"""Validate Week 4 factor inputs with the Week 2 data fetcher."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "week2"))

from week2.data_fetcher import get_daily_data, get_financial_data  # noqa: E402


def main() -> None:
    universe = pd.read_csv(ROOT / "week4/data/stock_universe.csv", dtype={"symbol": str})
    start_date = "20260101"
    end_date = "20260623"

    print("验证日线数据获取")
    for _, row in universe.iterrows():
        code = row["symbol"]
        name = row["name"]
        try:
            frame = get_daily_data(code, start_date, end_date, adjust="qfq")
            print(f"OK 日线 {code} {name}: {len(frame)} 行, 字段={list(frame.columns)[:8]}")
        except Exception as exc:  # noqa: BLE001 - validation should keep going
            print(f"FAIL 日线 {code} {name}: {type(exc).__name__}: {exc}")

    print("\n验证财务数据获取")
    for _, row in universe.iterrows():
        code = row["symbol"]
        name = row["name"]
        try:
            frame = get_financial_data(code)
            print(f"OK 财务 {code} {name}: {len(frame)} 行, 字段={list(frame.columns)[:6]}")
        except Exception as exc:  # noqa: BLE001 - validation should keep going
            print(f"FAIL 财务 {code} {name}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
