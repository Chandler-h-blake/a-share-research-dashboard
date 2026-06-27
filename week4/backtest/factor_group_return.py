"""Calculate quantile group returns for each factor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "week4"))

from factors import FACTOR_LIBRARY  # noqa: E402


DEFAULT_MERGED_PATH = ROOT / "week4/data/backtest/factor_with_forward_returns_20260520_20d.csv"
DEFAULT_OUTPUT_PATH = ROOT / "week4/data/backtest/factor_group_return_20260520_20d.csv"
DEFAULT_SUMMARY_PATH = ROOT / "week4/data/backtest/factor_group_summary_20260520_20d.csv"


def factor_columns(frame: pd.DataFrame) -> list[str]:
    return [factor for factor in FACTOR_LIBRARY if factor in frame.columns]


def assign_groups(adjusted_factor: pd.Series, group_count: int) -> pd.Series:
    """Assign group 1 to the highest adjusted factor values."""

    ranks = adjusted_factor.rank(method="first", ascending=False)
    groups = np.ceil(ranks / len(adjusted_factor) * group_count).astype(int)
    return pd.Series(groups.clip(1, group_count), index=adjusted_factor.index)


def calculate_group_returns(
    merged: pd.DataFrame,
    holding_days: int,
    group_count: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return_column = f"forward_return_{holding_days}d"
    if return_column not in merged.columns:
        raise ValueError(f"合并样本缺少字段：{return_column}")

    group_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    for factor in factor_columns(merged):
        meta = FACTOR_LIBRARY[factor]
        sample = merged[["symbol", "name", factor, return_column]].copy()
        sample[factor] = pd.to_numeric(sample[factor], errors="coerce")
        sample[return_column] = pd.to_numeric(sample[return_column], errors="coerce")
        sample = sample.dropna()
        if len(sample) < group_count:
            raise ValueError(f"{factor} 可用样本不足，无法分 {group_count} 组。")

        sample["adjusted_factor"] = sample[factor] * meta.direction
        sample["group"] = assign_groups(sample["adjusted_factor"], group_count)

        grouped = sample.groupby("group", as_index=False)[return_column].agg(
            count="count",
            mean_return="mean",
            median_return="median",
            min_return="min",
            max_return="max",
        )
        group_means = dict(zip(grouped["group"], grouped["mean_return"]))
        long_short = group_means.get(1) - group_means.get(group_count)

        for _, row in grouped.iterrows():
            group_rows.append(
                {
                    "factor": factor,
                    "name": meta.name,
                    "category": meta.category,
                    "direction": meta.direction,
                    "group": int(row["group"]),
                    "group_label": "top" if int(row["group"]) == 1 else "bottom" if int(row["group"]) == group_count else "middle",
                    "count": int(row["count"]),
                    "mean_return": row["mean_return"],
                    "median_return": row["median_return"],
                    "min_return": row["min_return"],
                    "max_return": row["max_return"],
                    f"group1_minus_group{group_count}": long_short,
                }
            )

        summary_rows.append(
            {
                "factor": factor,
                "name": meta.name,
                "category": meta.category,
                "direction": meta.direction,
                "top_group_mean_return": group_means.get(1),
                "bottom_group_mean_return": group_means.get(group_count),
                f"group1_minus_group{group_count}": long_short,
                "n": len(sample),
            }
        )

    group_result = pd.DataFrame(group_rows)
    summary = pd.DataFrame(summary_rows).sort_values(f"group1_minus_group{group_count}", ascending=False)
    return group_result, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged", type=Path, default=DEFAULT_MERGED_PATH)
    parser.add_argument("--holding-days", type=int, default=20)
    parser.add_argument("--groups", type=int, default=5)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    merged = pd.read_csv(args.merged, dtype={"symbol": str})
    group_returns, summary = calculate_group_returns(
        merged=merged,
        holding_days=args.holding_days,
        group_count=args.groups,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    group_returns.to_csv(args.output, index=False, encoding="utf-8-sig")
    summary.to_csv(args.summary, index=False, encoding="utf-8-sig")

    spread_column = f"group1_minus_group{args.groups}"
    print("分层收益计算完成")
    print(f"分组收益表：{args.output}，共 {len(group_returns)} 行")
    print(f"分层汇总表：{args.summary}，共 {len(summary)} 行")
    print(summary[["factor", "name", "top_group_mean_return", "bottom_group_mean_return", spread_column]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
