"""Run strict factor backtests for multiple as-of dates.

This script reuses the Week 4 backtest modules and writes one full set of
outputs per snapshot:

- strict as-of raw factors
- multi-factor scores and top pool
- 20-trading-day forward returns
- single-factor IC
- five-group return validation

It also writes combined summary files that are useful for the next step:
deriving a more defensible factor weight configuration from multiple snapshots.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "week4"))
sys.path.insert(0, str(ROOT / "week4/backtest"))

from build_asof_factors import build_factor_table_asof  # noqa: E402
from factor_group_return import calculate_group_returns  # noqa: E402
from factor_ic import calculate_ic  # noqa: E402
from factor_scoring import FACTOR_WEIGHTS, score_factors, select_top_pool  # noqa: E402
from forward_returns import build_forward_returns  # noqa: E402


DEFAULT_ASOF_DATES = ["20260410", "20260430", "20260508"]
DEFAULT_START_DATE = "20260101"
DEFAULT_UNIVERSE_PATH = ROOT / "week4/data/hs300_universe.csv"
DEFAULT_DISCLOSURE_PATH = ROOT / "week4/data/backtest/disclosure_calendar.csv"
DEFAULT_CACHE_DIR = ROOT / "week4/data/cache"
DEFAULT_OUTPUT_DIR = ROOT / "week4/data/backtest"


def output_paths(output_dir: Path, asof_date: str, holding_days: int) -> dict[str, Path]:
    suffix = f"{asof_date}_{holding_days}d"
    return {
        "factor_raw": output_dir / f"factor_raw_{asof_date}.csv",
        "factor_errors": output_dir / f"factor_errors_{asof_date}.csv",
        "factor_scores": output_dir / f"factor_scores_{asof_date}.csv",
        "top_pool": output_dir / f"top30_stock_pool_{asof_date}.csv",
        "forward_returns": output_dir / f"forward_returns_{suffix}.csv",
        "forward_errors": output_dir / f"forward_return_errors_{suffix}.csv",
        "ic": output_dir / f"factor_ic_{suffix}.csv",
        "merged": output_dir / f"factor_with_forward_returns_{suffix}.csv",
        "group_returns": output_dir / f"factor_group_return_{suffix}.csv",
        "group_summary": output_dir / f"factor_group_summary_{suffix}.csv",
    }


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def ensure_asof_column(frame: pd.DataFrame, asof_date: str) -> pd.DataFrame:
    result = frame.copy()
    if "asof_date" in result.columns:
        result["asof_date"] = asof_date
        columns = ["asof_date"] + [column for column in result.columns if column != "asof_date"]
        return result[columns]

    result.insert(0, "asof_date", asof_date)
    return result


def run_snapshot(
    asof_date: str,
    start_date: str,
    universe_path: Path,
    disclosure_path: Path,
    cache_dir: Path,
    output_dir: Path,
    holding_days: int,
    group_count: int,
    top_n: int,
    refresh: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    paths = output_paths(output_dir, asof_date, holding_days)

    print(f"\n========== 截面日 {asof_date} ==========")
    factors, factor_errors = build_factor_table_asof(
        universe_path=universe_path,
        disclosure_path=disclosure_path,
        start_date=start_date,
        asof_date=asof_date,
        cache_dir=cache_dir,
        refresh=refresh,
        resume_from=None,
    )
    write_csv(factors, paths["factor_raw"])
    write_csv(factor_errors, paths["factor_errors"])
    print(f"严格截面因子：{paths['factor_raw']}，共 {len(factors)} 行")
    print(f"因子错误表：{paths['factor_errors']}，共 {len(factor_errors)} 行")

    if factors.empty:
        raise ValueError(f"{asof_date} 没有可用于回测的因子样本。")

    scores = score_factors(factors, FACTOR_WEIGHTS)
    top_pool = select_top_pool(scores, top_n=top_n)
    write_csv(scores, paths["factor_scores"])
    write_csv(top_pool, paths["top_pool"])
    print(f"多因子得分：{paths['factor_scores']}，TOP{top_n}：{paths['top_pool']}")

    forward_returns, forward_errors = build_forward_returns(
        factor_path=paths["factor_raw"],
        cache_dir=cache_dir,
        holding_days=holding_days,
    )
    write_csv(forward_returns, paths["forward_returns"])
    write_csv(forward_errors, paths["forward_errors"])
    print(f"未来收益：{paths['forward_returns']}，共 {len(forward_returns)} 行")
    print(f"未来收益错误表：{paths['forward_errors']}，共 {len(forward_errors)} 行")

    ic, merged = calculate_ic(
        factors=factors,
        forward_returns=forward_returns,
        holding_days=holding_days,
    )
    ic = ensure_asof_column(ic, asof_date)
    merged = ensure_asof_column(merged, asof_date)
    write_csv(ic, paths["ic"])
    write_csv(merged, paths["merged"])
    print(f"IC：{paths['ic']}，合并样本：{paths['merged']}")

    group_returns, group_summary = calculate_group_returns(
        merged=merged,
        holding_days=holding_days,
        group_count=group_count,
    )
    group_returns = ensure_asof_column(group_returns, asof_date)
    group_summary = ensure_asof_column(group_summary, asof_date)
    write_csv(group_returns, paths["group_returns"])
    write_csv(group_summary, paths["group_summary"])
    print(f"五组分层：{paths['group_summary']}")

    return ic, group_summary


def aggregate_performance(
    ic_summary: pd.DataFrame,
    group_summary: pd.DataFrame,
    group_count: int,
) -> pd.DataFrame:
    spread_column = f"group1_minus_group{group_count}"
    merged = ic_summary.merge(
        group_summary[["asof_date", "factor", spread_column]],
        on=["asof_date", "factor"],
        how="left",
    )

    rows: list[dict[str, object]] = []
    for factor, sample in merged.groupby("factor"):
        rows.append(
            {
                "factor": factor,
                "name": sample["name"].iloc[0],
                "category": sample["category"].iloc[0],
                "direction": sample["direction"].iloc[0],
                "snapshot_count": sample["asof_date"].nunique(),
                "avg_n": sample["n"].mean(),
                "avg_spearman_ic_adjusted": sample["spearman_ic_adjusted"].mean(),
                "ic_positive_rate": (sample["spearman_ic_adjusted"] > 0).mean(),
                "avg_pearson_ic_adjusted": sample["pearson_ic_adjusted"].mean(),
                "avg_group1_minus_group5": sample[spread_column].mean(),
                "group_spread_positive_rate": (sample[spread_column] > 0).mean(),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["avg_spearman_ic_adjusted", "avg_group1_minus_group5"],
        ascending=[False, False],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asof-dates", nargs="+", default=DEFAULT_ASOF_DATES)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--disclosure-calendar", type=Path, default=DEFAULT_DISCLOSURE_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--holding-days", type=int, default=20)
    parser.add_argument("--groups", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    all_ic: list[pd.DataFrame] = []
    all_group_summary: list[pd.DataFrame] = []

    for asof_date in args.asof_dates:
        ic, group_summary = run_snapshot(
            asof_date=asof_date,
            start_date=args.start_date,
            universe_path=args.universe,
            disclosure_path=args.disclosure_calendar,
            cache_dir=args.cache_dir,
            output_dir=args.output_dir,
            holding_days=args.holding_days,
            group_count=args.groups,
            top_n=args.top_n,
            refresh=args.refresh,
        )
        all_ic.append(ic)
        all_group_summary.append(group_summary)

    ic_summary = pd.concat(all_ic, ignore_index=True)
    group_summary = pd.concat(all_group_summary, ignore_index=True)
    performance = aggregate_performance(ic_summary, group_summary, args.groups)

    write_csv(ic_summary, args.output_dir / "multi_snapshot_ic_summary.csv")
    write_csv(group_summary, args.output_dir / "multi_snapshot_group_summary.csv")
    write_csv(performance, args.output_dir / "multi_snapshot_factor_performance.csv")

    print("\n========== 多截面汇总 ==========")
    print(f"IC 汇总：{args.output_dir / 'multi_snapshot_ic_summary.csv'}")
    print(f"分层汇总：{args.output_dir / 'multi_snapshot_group_summary.csv'}")
    print(f"因子表现汇总：{args.output_dir / 'multi_snapshot_factor_performance.csv'}")
    print(
        performance[
            [
                "factor",
                "name",
                "snapshot_count",
                "avg_spearman_ic_adjusted",
                "ic_positive_rate",
                "avg_group1_minus_group5",
                "group_spread_positive_rate",
            ]
        ].to_string(index=False)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
