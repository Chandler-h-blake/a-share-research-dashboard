"""生成沪深300股票池 CSV。

输出文件默认是：
    week4/data/hs300_universe.csv

这个文件会被 factor_ranking.py 读取。列名保持和 10 只观察股股票池一致：
    symbol,name,industry
"""

from __future__ import annotations

import argparse
from pathlib import Path

import akshare as ak
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = ROOT / "week4/data/hs300_universe.csv"


def build_hs300_universe() -> pd.DataFrame:
    """从中证指数成分股接口获取当前沪深300成分股。

    注意：
    这里拿到的是“当前”沪深300成分股，适合做当前截面排名。
    如果将来做严格历史回测，不能直接把当前成分股倒推到过去。
    """

    raw = ak.index_stock_cons_csindex(symbol="000300")
    rename_map = {
        "成分券代码": "symbol",
        "品种代码": "symbol",
        "股票代码": "symbol",
        "代码": "symbol",
        "成分券名称": "name",
        "品种名称": "name",
        "股票名称": "name",
        "名称": "name",
        "行业": "industry",
        "中证一级行业": "industry",
        "申万一级行业": "industry",
    }
    universe = raw.rename(columns=rename_map).copy()

    if "symbol" not in universe.columns or "name" not in universe.columns:
        raise ValueError(f"沪深300接口字段不符合预期，实际字段：{list(raw.columns)}")

    universe["symbol"] = universe["symbol"].astype(str).str.extract(r"(\d{6})")[0]
    universe["name"] = universe["name"].astype(str).str.strip()
    if "industry" not in universe.columns:
        universe["industry"] = "unknown"
    universe["industry"] = universe["industry"].fillna("unknown").astype(str).str.strip()

    universe = universe.dropna(subset=["symbol"])
    universe = universe[["symbol", "name", "industry"]].drop_duplicates("symbol")
    return universe.sort_values("symbol").reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="调试用：只输出前 N 只股票。正式跑沪深300时不要传。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    universe = build_hs300_universe()
    if args.limit is not None:
        universe = universe.head(args.limit)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    universe.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"沪深300股票池已生成：{args.output}，共 {len(universe)} 只")
    print(universe.head(10).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
