"""第4周 4.3：多因子标准化、加权打分和股票排名。

这个脚本接在 4.2 后面使用：

1. 读取 week4/data/factor_raw.csv
2. 对每个原始因子做 Z-score 标准化
3. 按因子方向调整，让所有得分都变成“越高越好”
4. 按权重合成 composite_score
5. 输出完整得分表 factor_scores.csv
6. 输出精选股票池 top_stock_pool.csv

注意：
这里做的是课程项目里的第一版多因子打分系统。权重是人为设定的，
后面可以结合 IC、分层回测结果再调整。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from factors import FACTOR_LIBRARY, direction_adjusted_zscore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = ROOT / "week4/data/factor_raw.csv"
DEFAULT_SCORE_PATH = ROOT / "week4/data/factor_scores.csv"
DEFAULT_TOP_PATH = ROOT / "week4/data/top_stock_pool.csv"


# 4.3 第一版权重。
# 权重总和为 1。这里把价值、质量、成长、动量和风险都放进去，
# 避免模型只偏向某一个角度。
FACTOR_WEIGHTS: dict[str, float] = {
    "momentum_20d": 0.15,
    "turnover_change": 0.08,
    "pe_percentile": 0.12,
    "pb_percentile": 0.10,
    "roe": 0.15,
    "gross_margin": 0.12,
    "revenue_growth_yoy": 0.10,
    "net_profit_growth_yoy": 0.10,
    "volatility_60d": 0.08,
}


def validate_weights(weights: dict[str, float]) -> None:
    """检查权重配置，避免后面算出看似正常但其实没意义的分数。"""

    total_weight = sum(weights.values())
    if not weights:
        raise ValueError("权重不能为空。")
    if any(weight < 0 for weight in weights.values()):
        raise ValueError("权重不能为负数。")
    if abs(total_weight - 1.0) > 1e-8:
        raise ValueError(f"权重总和必须为 1，目前是 {total_weight:.6f}。")


def score_factors(raw: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    """把原始因子表转换成得分表。

    原始因子的单位不一样，比如：
    - ROE 是百分数；
    - 动量是收益率；
    - PE/PB 分位数在 0 到 1 之间；
    - 波动率是年化标准差。

    所以不能直接相加，必须先做 Z-score 标准化。
    """

    validate_weights(weights)

    result = raw.copy()
    score_columns: list[str] = []

    for factor, weight in weights.items():
        if factor not in result.columns:
            raise ValueError(f"factor_raw.csv 缺少因子列：{factor}")
        if factor not in FACTOR_LIBRARY:
            raise ValueError(f"FACTOR_LIBRARY 缺少因子说明：{factor}")

        meta = FACTOR_LIBRARY[factor]
        score_column = f"{factor}_score"

        # direction_adjusted_zscore 会同时完成两件事：
        # 1. 标准化：变成均值约为 0、标准差约为 1 的分数；
        # 2. 方向调整：PE/PB/波动率这类“越低越好”的因子会乘以 -1。
        result[score_column] = direction_adjusted_zscore(
            result[factor],
            direction=meta.direction,
        )
        result[f"{factor}_weighted_score"] = result[score_column] * weight
        score_columns.append(f"{factor}_weighted_score")

    result["composite_score"] = result[score_columns].sum(axis=1)
    result["rank"] = result["composite_score"].rank(
        ascending=False,
        method="min",
    ).astype(int)

    return result.sort_values(["rank", "symbol"]).reset_index(drop=True)


def select_top_pool(scores: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """从得分表里选出综合分最高的股票池。"""

    columns = [
        "rank",
        "symbol",
        "name",
        "industry",
        "composite_score",
        "momentum_20d",
        "pe_percentile",
        "pb_percentile",
        "roe",
        "gross_margin",
        "revenue_growth_yoy",
        "net_profit_growth_yoy",
        "volatility_60d",
    ]
    existing_columns = [column for column in columns if column in scores.columns]
    return scores.head(top_n)[existing_columns].copy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--scores", type=Path, default=DEFAULT_SCORE_PATH)
    parser.add_argument("--top", type=Path, default=DEFAULT_TOP_PATH)
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="当前股票池只有10只，默认先输出TOP5；扩展到沪深300后可以改成30。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    raw = pd.read_csv(args.input, dtype={"symbol": str})

    scores = score_factors(raw, FACTOR_WEIGHTS)
    top_pool = select_top_pool(scores, top_n=args.top_n)

    args.scores.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(args.scores, index=False, encoding="utf-8-sig")
    top_pool.to_csv(args.top, index=False, encoding="utf-8-sig")

    print("多因子打分完成")
    print(f"完整得分表：{args.scores}，共 {len(scores)} 行")
    print(f"精选股票池：{args.top}，共 {len(top_pool)} 行")
    print("\nTOP结果：")
    print(top_pool[["rank", "symbol", "name", "composite_score"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
