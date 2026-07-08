"""第六周 6.2：申万一级行业轮动数据生成。

输出:
    week6/data/industry_rotation.csv

脚本使用 AkShare 申万一级行业历史行情，计算近 1 月和近 3 月收益率、
排名和轮动分类，供最终看板的「行业轮动」页面读取。
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Any

import pandas as pd

try:
    import akshare as ak
except ImportError as exc:  # pragma: no cover - 运行环境依赖
    raise RuntimeError("当前环境没有安装 akshare，请先安装 requirements.txt 中的依赖。") from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "week6/data/industry_rotation.csv"


def normalize_industry_code(value: Any) -> str:
    """AkShare 行业代码可能是 801050.SI，历史行情接口需要 801050。"""

    return str(value).strip().split(".")[0]


def pick_column(df: pd.DataFrame, candidates: list[str]) -> str:
    for column in candidates:
        if column in df.columns:
            return column
    raise RuntimeError(f"接口返回字段中找不到候选列：{candidates}，实际字段：{df.columns.tolist()}")


def load_sw_first_industries() -> pd.DataFrame:
    """读取申万一级行业代码表。"""

    raw = ak.sw_index_first_info()
    if raw.empty:
        raise RuntimeError("sw_index_first_info 返回空表")

    code_col = pick_column(raw, ["行业代码", "指数代码", "代码", "index_code", "symbol"])
    name_col = pick_column(raw, ["行业名称", "指数名称", "名称", "name"])
    result = raw[[code_col, name_col]].copy()
    result.columns = ["industry_code", "industry_name"]
    result["industry_code"] = result["industry_code"].map(normalize_industry_code)
    result["industry_name"] = result["industry_name"].astype(str).str.strip()
    result = result.dropna().drop_duplicates("industry_code")
    return result.reset_index(drop=True)


def load_industry_history(industry_code: str) -> pd.DataFrame:
    """读取单个申万行业历史日线。"""

    raw = ak.index_hist_sw(symbol=industry_code, period="day")
    if raw.empty:
        raise RuntimeError(f"{industry_code} 历史行情为空")

    date_col = pick_column(raw, ["日期", "date", "交易日期"])
    close_col = pick_column(raw, ["收盘", "close", "收盘价"])
    result = raw[[date_col, close_col]].copy()
    result.columns = ["date", "close"]
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result = result.dropna(subset=["date", "close"]).sort_values("date")
    if len(result) < 20:
        raise RuntimeError(f"{industry_code} 可用历史行情不足 20 条")
    return result.reset_index(drop=True)


def build_local_proxy_rotation() -> pd.DataFrame:
    """外部行情接口不可用时，用本地 TOP 股票池构造演示用行业强弱代理。

    该结果不是行业指数历史收益率，因此 data_source 会明确标注为本地因子代理。
    """

    scores_path = ROOT / "week4/data/final_factor_scores.csv"
    mapping_path = ROOT / "week5/industry_mapping.csv"
    if not scores_path.exists() or not mapping_path.exists():
        raise RuntimeError("本地降级需要 week4 final_factor_scores.csv 和 week5 industry_mapping.csv")

    scores = pd.read_csv(scores_path, dtype={"symbol": str}, encoding="utf-8-sig")
    mapping = pd.read_csv(mapping_path, dtype={"symbol": str, "industry_code": str}, encoding="utf-8-sig")
    scores["symbol"] = scores["symbol"].astype(str).str.zfill(6)
    mapping["symbol"] = mapping["symbol"].astype(str).str.zfill(6)
    merged = scores.merge(mapping[["symbol", "industry", "industry_code"]], on="symbol", how="inner", suffixes=("", "_mapped"))
    if "industry_mapped" in merged.columns:
        merged["industry"] = merged["industry_mapped"].fillna(merged.get("industry"))
    merged = merged.dropna(subset=["industry"])
    if merged.empty:
        raise RuntimeError("本地行业映射为空，无法生成行业轮动代理数据")

    grouped = (
        merged.groupby(["industry_code", "industry"], dropna=False)
        .agg(
            return_1m=("momentum_20d", "mean"),
            composite_score=("composite_score", "mean"),
            stock_count=("symbol", "count"),
            latest_close=("composite_score", "mean"),
        )
        .reset_index()
    )
    max_abs = grouped["composite_score"].abs().max()
    if pd.isna(max_abs) or max_abs == 0:
        grouped["return_3m"] = grouped["return_1m"]
    else:
        grouped["return_3m"] = grouped["composite_score"] / max_abs * 0.12

    grouped = grouped.rename(columns={"industry": "industry_name"})
    grouped["last_date"] = datetime.now().strftime("%Y-%m-%d")
    grouped["history_rows"] = grouped["stock_count"]
    grouped["data_source"] = "本地 TOP 股票池因子代理（非行业指数历史行情）"
    return grouped[
        [
            "industry_code",
            "industry_name",
            "last_date",
            "latest_close",
            "return_1m",
            "return_3m",
            "history_rows",
            "data_source",
        ]
    ]


def pct_return(history: pd.DataFrame, window: int) -> float | None:
    if len(history) <= window:
        return None
    latest = float(history["close"].iloc[-1])
    base = float(history["close"].iloc[-window - 1])
    if base == 0:
        return None
    return latest / base - 1


def classify_rotation(rank_1m: int, rank_3m: int, total: int) -> str:
    strong_cut = max(1, round(total * 0.33))
    weak_cut = max(1, round(total * 0.67))
    if rank_1m <= strong_cut and rank_3m <= strong_cut:
        return "持续强势"
    if rank_1m <= strong_cut and rank_3m > weak_cut:
        return "短期转强"
    if rank_1m > weak_cut and rank_3m <= strong_cut:
        return "中期强势"
    if rank_1m > weak_cut and rank_3m > weak_cut:
        return "持续走弱"
    return "震荡中性"


def build_industry_rotation(sleep_seconds: float = 0.15) -> pd.DataFrame:
    industries = load_sw_first_industries()
    records: list[dict[str, object]] = []
    errors: list[str] = []

    for _, row in industries.iterrows():
        code = str(row["industry_code"])
        name = str(row["industry_name"])
        try:
            history = load_industry_history(code)
            records.append(
                {
                    "industry_code": code,
                    "industry_name": name,
                    "last_date": history["date"].iloc[-1].strftime("%Y-%m-%d"),
                    "latest_close": float(history["close"].iloc[-1]),
                    "return_1m": pct_return(history, 20),
                    "return_3m": pct_return(history, 60),
                    "history_rows": len(history),
                    "data_source": "AkShare index_hist_sw / 申万一级行业指数",
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{code} {name}: {exc}")
        sleep(sleep_seconds)

    if not records:
        print("真实行业历史接口全部失败，改用本地因子代理数据。失败样例：" + "；".join(errors[:5]))
        result = build_local_proxy_rotation()
    else:
        result = pd.DataFrame(records)

    result = result.dropna(subset=["return_1m", "return_3m"]).copy()
    if result.empty:
        raise RuntimeError("行业轮动收益率全部为空")

    result["rank_1m"] = result["return_1m"].rank(ascending=False, method="min").astype(int)
    result["rank_3m"] = result["return_3m"].rank(ascending=False, method="min").astype(int)
    total = len(result)
    result["rotation_type"] = [
        classify_rotation(int(row["rank_1m"]), int(row["rank_3m"]), total)
        for _, row in result.iterrows()
    ]
    result["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return result.sort_values("rank_1m").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成申万一级行业轮动数据")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出 CSV 路径")
    parser.add_argument("--sleep", type=float, default=0.15, help="每个行业请求后的等待秒数")
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = build_industry_rotation(sleep_seconds=args.sleep)
    result.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"行业轮动数据已生成：{output}")
    print(f"行业数量：{len(result)}，更新时间：{result['generated_at'].iloc[0]}")


if __name__ == "__main__":
    main()
