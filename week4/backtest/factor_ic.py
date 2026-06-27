"""Calculate single-factor IC against forward returns."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "week4"))

from factors import FACTOR_LIBRARY  # noqa: E402


DEFAULT_FACTOR_PATH = ROOT / "week4/data/backtest/factor_raw_20260520.csv"
DEFAULT_FORWARD_RETURN_PATH = ROOT / "week4/data/backtest/forward_returns_20260520_20d.csv"
DEFAULT_OUTPUT_PATH = ROOT / "week4/data/backtest/factor_ic_20260520_20d.csv"
DEFAULT_MERGED_PATH = ROOT / "week4/data/backtest/factor_with_forward_returns_20260520_20d.csv"


def factor_columns(frame: pd.DataFrame) -> list[str]:
    return [factor for factor in FACTOR_LIBRARY if factor in frame.columns]


def _spearman_without_scipy(left: pd.Series, right: pd.Series) -> float:
    """Calculate Spearman correlation as Pearson correlation of ranks."""

    return left.rank(method="average").corr(right.rank(method="average"), method="pearson")


def calculate_ic(
    factors: pd.DataFrame,
    forward_returns: pd.DataFrame,
    holding_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return_column = f"forward_return_{holding_days}d"
    merged = factors.merge(forward_returns, on=["symbol", "name"], how="inner")
    if return_column not in merged.columns:
        raise ValueError(f"未来收益表缺少字段：{return_column}")

    rows: list[dict[str, object]] = []
    for factor in factor_columns(merged):
        meta = FACTOR_LIBRARY[factor]
        sample = merged[[factor, return_column]].copy()
        sample[factor] = pd.to_numeric(sample[factor], errors="coerce")
        sample[return_column] = pd.to_numeric(sample[return_column], errors="coerce")
        sample = sample.dropna()
        if len(sample) < 3:
            raise ValueError(f"{factor} 可用样本不足，无法计算 IC。")

        pearson_raw = sample[factor].corr(sample[return_column], method="pearson")
        spearman_raw = _spearman_without_scipy(sample[factor], sample[return_column])
        rows.append(
            {
                "factor": factor,
                "name": meta.name,
                "category": meta.category,
                "direction": meta.direction,
                "n": len(sample),
                "pearson_ic_raw": pearson_raw,
                "spearman_ic_raw": spearman_raw,
                "pearson_ic_adjusted": pearson_raw * meta.direction,
                "spearman_ic_adjusted": spearman_raw * meta.direction,
            }
        )

    result = pd.DataFrame(rows)
    return result.sort_values("spearman_ic_adjusted", ascending=False), merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factors", type=Path, default=DEFAULT_FACTOR_PATH)
    parser.add_argument("--forward-returns", type=Path, default=DEFAULT_FORWARD_RETURN_PATH)
    parser.add_argument("--holding-days", type=int, default=20)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--merged-output", type=Path, default=DEFAULT_MERGED_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    factors = pd.read_csv(args.factors, dtype={"symbol": str})
    forward_returns = pd.read_csv(args.forward_returns, dtype={"symbol": str})
    ic, merged = calculate_ic(factors, forward_returns, args.holding_days)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ic.to_csv(args.output, index=False, encoding="utf-8-sig")
    merged.to_csv(args.merged_output, index=False, encoding="utf-8-sig")

    print("IC 计算完成")
    print(f"IC 表：{args.output}，共 {len(ic)} 行")
    print(f"合并样本：{args.merged_output}，共 {len(merged)} 行")
    print(ic[["factor", "name", "spearman_ic_adjusted", "pearson_ic_adjusted", "n"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
