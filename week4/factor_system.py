"""第4周多因子打分系统主入口。

这个文件面向后续 Streamlit 看板整合：

1. 读取已经生成好的原始因子表；
2. 读取权重配置，默认使用 factor_scoring.py 里的第四周最终版权重；
3. 调用 factor_scoring.py 的标准化、方向调整和加权打分逻辑；
4. 输出看板直接可读的 final_* 文件。

注意：
这个主入口默认不重新抓取行情/财务/估值数据。批量数据抓取仍由
factor_ranking.py 负责；这里专注于“把已有因子表转成最终看板产物”。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from factor_scoring import FACTOR_WEIGHTS, score_factors, select_top_pool
from factors import FACTOR_LIBRARY


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_PATH = ROOT / "week4/data/hs300_factor_raw.csv"
DEFAULT_SCORES_PATH = ROOT / "week4/data/final_factor_scores.csv"
DEFAULT_TOP_PATH = ROOT / "week4/data/final_top30_stock_pool.csv"
DEFAULT_WEIGHTS_OUTPUT_PATH = ROOT / "week4/data/final_factor_weights.json"
DEFAULT_OVERVIEW_PATH = ROOT / "week4/data/final_factor_overview.csv"
DEFAULT_VALIDATION_PATH = ROOT / "week4/data/backtest/multi_snapshot_4dates_factor_performance.csv"


def load_weights(path: Path | None) -> dict[str, float]:
    """读取权重配置。

    支持两种 JSON 格式：
    1. 直接是 {"momentum_20d": 0.15, ...}
    2. 包一层 {"weights": {"momentum_20d": 0.15, ...}}

    如果不传 path，则使用 factor_scoring.py 中的第四周最终版权重。
    """

    if path is None:
        return FACTOR_WEIGHTS.copy()

    with path.open("r", encoding="utf-8") as file:
        payload: Any = json.load(file)

    weights = payload.get("weights", payload) if isinstance(payload, dict) else payload
    if not isinstance(weights, dict):
        raise ValueError("权重文件必须是 JSON 对象。")

    return {str(factor): float(weight) for factor, weight in weights.items()}


def write_weight_snapshot(weights: dict[str, float], output_path: Path) -> None:
    """写出最终权重快照，方便看板展示和后续追踪版本。"""

    factors = []
    for factor, weight in weights.items():
        meta = FACTOR_LIBRARY.get(factor)
        factors.append(
            {
                "factor": factor,
                "name": meta.name if meta else factor,
                "category": meta.category if meta else "unknown",
                "direction": meta.direction if meta else None,
                "weight": weight,
                "description": meta.description if meta else "",
            }
        )

    payload = {
        "version": "v2_week4_final",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "basis": "20260410、20260430、20260508、20260520 四个截面的 20 日收益 IC 与五组分层验证",
        "weight_sum": sum(weights.values()),
        "weights": weights,
        "factors": factors,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def load_validation_summary(path: Path | None) -> pd.DataFrame:
    """读取回测验证摘要；如果没有文件，就返回空表。"""

    if path is None or not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def build_factor_overview(
    weights: dict[str, float],
    validation: pd.DataFrame,
) -> pd.DataFrame:
    """生成因子概览表，供看板展示权重、方向和验证指标。"""

    rows: list[dict[str, object]] = []
    validation_by_factor: dict[str, dict[str, object]] = {}
    if not validation.empty and "factor" in validation.columns:
        validation_by_factor = {
            str(row["factor"]): row.to_dict()
            for _, row in validation.iterrows()
        }

    for factor, weight in weights.items():
        if factor not in FACTOR_LIBRARY:
            raise ValueError(f"FACTOR_LIBRARY 缺少因子说明：{factor}")
        meta = FACTOR_LIBRARY[factor]
        validation_row = validation_by_factor.get(factor, {})
        rows.append(
            {
                "factor": factor,
                "name": meta.name,
                "category": meta.category,
                "direction": meta.direction,
                "direction_text": "越高越好" if meta.direction == 1 else "越低越好",
                "weight": weight,
                "data_source": meta.data_source,
                "description": meta.description,
                "spearman_ic_adjusted": validation_row.get(
                    "avg_spearman_ic_adjusted",
                    validation_row.get("spearman_ic_adjusted"),
                ),
                "pearson_ic_adjusted": validation_row.get(
                    "avg_pearson_ic_adjusted",
                    validation_row.get("pearson_ic_adjusted"),
                ),
                "ic_positive_rate": validation_row.get("ic_positive_rate"),
                "group1_minus_group5": validation_row.get("avg_group1_minus_group5"),
                "group_spread_positive_rate": validation_row.get("group_spread_positive_rate"),
                "validation_n": validation_row.get("avg_n", validation_row.get("n")),
                "snapshot_count": validation_row.get("snapshot_count"),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["weight", "factor"],
        ascending=[False, True],
    )


def build_factor_system_outputs(
    raw_path: Path,
    weights: dict[str, float],
    scores_path: Path,
    top_path: Path,
    weights_output_path: Path,
    overview_path: Path,
    validation_path: Path | None,
    top_n: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """生成看板用最终产物。"""

    raw = pd.read_csv(raw_path, dtype={"symbol": str})
    scores = score_factors(raw, weights)
    top_pool = select_top_pool(scores, top_n=top_n)
    validation = load_validation_summary(validation_path)
    overview = build_factor_overview(weights, validation)

    scores_path.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(scores_path, index=False, encoding="utf-8-sig")
    top_pool.to_csv(top_path, index=False, encoding="utf-8-sig")
    overview.to_csv(overview_path, index=False, encoding="utf-8-sig")
    write_weight_snapshot(weights, weights_output_path)

    return scores, top_pool, overview


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw",
        type=Path,
        default=DEFAULT_RAW_PATH,
        help="原始因子表，默认读取沪深300当前因子表。",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=None,
        help="可选：因子权重 JSON。不传则使用 factor_scoring.py 中的第四周最终版权重。",
    )
    parser.add_argument("--scores", type=Path, default=DEFAULT_SCORES_PATH)
    parser.add_argument("--top", type=Path, default=DEFAULT_TOP_PATH)
    parser.add_argument("--weights-output", type=Path, default=DEFAULT_WEIGHTS_OUTPUT_PATH)
    parser.add_argument("--overview", type=Path, default=DEFAULT_OVERVIEW_PATH)
    parser.add_argument(
        "--validation",
        type=Path,
        default=DEFAULT_VALIDATION_PATH,
        help="可选：单因子验证结果，用于生成因子概览表。",
    )
    parser.add_argument("--top-n", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    weights = load_weights(args.weights)
    scores, top_pool, overview = build_factor_system_outputs(
        raw_path=args.raw,
        weights=weights,
        scores_path=args.scores,
        top_path=args.top,
        weights_output_path=args.weights_output,
        overview_path=args.overview,
        validation_path=args.validation,
        top_n=args.top_n,
    )

    print("多因子系统产物生成完成")
    print(f"原始因子表：{args.raw}，共 {len(scores)} 只股票")
    print(f"最终得分表：{args.scores}")
    print(f"最终TOP股票池：{args.top}，共 {len(top_pool)} 只")
    print(f"最终权重：{args.weights_output}")
    print(f"因子概览：{args.overview}，共 {len(overview)} 个因子")
    print("\nTOP结果：")
    print(top_pool[["rank", "symbol", "name", "composite_score"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
