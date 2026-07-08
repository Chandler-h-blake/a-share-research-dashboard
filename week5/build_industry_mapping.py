"""为第五周研报股票生成申万一级行业映射表。

这个脚本只服务第五周，不改动第四周因子系统。

数据来源：
- AkShare sw_index_first_info：申万一级行业列表
- AkShare index_component_sw：申万行业指数成分股

运行：
    python week5/build_industry_mapping.py

默认读取：
    week4/data/final_top30_stock_pool.csv

默认输出：
    week5/industry_mapping.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOP_POOL_PATH = ROOT / "week4/data/final_top30_stock_pool.csv"
DEFAULT_OUTPUT_PATH = ROOT / "week5/industry_mapping.csv"
CNINFO_SW_STANDARD = "申银万国行业分类标准"


def normalize_symbol(value: Any) -> str:
    """把股票代码统一成 6 位字符串。"""

    return str(value).strip().zfill(6)


def normalize_industry_code(value: Any) -> str:
    """AkShare 行业代码可能是 801050.SI，成分接口需要 801050。"""

    return str(value).strip().split(".")[0]


def load_target_stocks(path: Path, top_n: int) -> pd.DataFrame:
    """读取需要补行业的股票列表。"""

    if not path.exists():
        raise FileNotFoundError(f"找不到 TOP 股票池文件：{path}")

    top_pool = pd.read_csv(path, dtype={"symbol": str}, encoding="utf-8-sig")
    required_columns = {"rank", "symbol", "name"}
    missing_columns = required_columns - set(top_pool.columns)
    if missing_columns:
        raise ValueError(f"TOP 股票池缺少字段：{sorted(missing_columns)}")

    result = top_pool.sort_values("rank").head(top_n).copy()
    result["symbol"] = result["symbol"].map(normalize_symbol)
    return result[["rank", "symbol", "name"]].reset_index(drop=True)


def fetch_sw_first_industries() -> pd.DataFrame:
    """获取申万一级行业列表。"""

    industries = ak.sw_index_first_info()
    required_columns = {"行业代码", "行业名称"}
    missing_columns = required_columns - set(industries.columns)
    if missing_columns:
        raise RuntimeError(f"申万一级行业接口缺少字段：{sorted(missing_columns)}")
    return industries[["行业代码", "行业名称"]].copy()


def find_industry_for_targets(
    targets: pd.DataFrame,
    industries: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """遍历申万一级行业成分股，为目标股票匹配行业。"""

    target_symbols = set(targets["symbol"].tolist())
    matches: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for _, industry in industries.iterrows():
        industry_code = normalize_industry_code(industry["行业代码"])
        industry_name = str(industry["行业名称"]).strip()

        try:
            components = ak.index_component_sw(symbol=industry_code)
        except Exception as exc:
            errors.append(f"{industry_code} {industry_name}: {exc}")
            continue

        required_columns = {"证券代码", "证券名称"}
        missing_columns = required_columns - set(components.columns)
        if missing_columns:
            errors.append(f"{industry_code} {industry_name}: 缺少字段 {sorted(missing_columns)}")
            continue

        components = components[["证券代码", "证券名称"]].copy()
        components["symbol"] = components["证券代码"].map(normalize_symbol)
        hit_components = components[components["symbol"].isin(target_symbols)]

        for _, component in hit_components.iterrows():
            symbol = str(component["symbol"])
            matches[symbol] = {
                "industry": industry_name,
                "industry_code": industry_code,
                "matched_name": str(component["证券名称"]).strip(),
            }

        if len(matches) == len(target_symbols):
            break

    rows: list[dict[str, Any]] = []
    for _, stock in targets.iterrows():
        symbol = str(stock["symbol"])
        match = matches.get(symbol, {})
        rows.append(
            {
                "symbol": symbol,
                "name": stock["name"],
                "industry": match.get("industry", "未识别"),
                "industry_code": match.get("industry_code", ""),
                "matched_name": match.get("matched_name", ""),
                "source": "AkShare sw_index_first_info + index_component_sw",
            }
        )

    return pd.DataFrame(rows), errors


def fetch_cninfo_sw_industry(symbol: str) -> dict[str, str] | None:
    """用巨潮行业变更接口按股票代码查询申万行业分类。

    index_component_sw 受 AkShare/源站字段变化影响时，可能无法反查成分股。
    该接口按证券代码返回历史分类记录，优先取最新的“申银万国行业分类标准”
    记录，用其中“行业门类”作为申万一级行业。
    """

    last_error: Exception | None = None
    for _ in range(3):
        try:
            history = ak.stock_industry_change_cninfo(
                symbol=symbol,
                start_date="20000101",
                end_date="20260707",
            )
        except Exception as exc:  # noqa: BLE001 - 外部接口偶发返回空 JSON，需要重试
            last_error = exc
            continue

        if history.empty or "分类标准" not in history.columns:
            return None

        rows = history[
            history["分类标准"].astype(str).str.contains(CNINFO_SW_STANDARD, na=False)
        ].copy()
        if rows.empty:
            return None
        if "变更日期" in rows.columns:
            rows["变更日期"] = pd.to_datetime(rows["变更日期"], errors="coerce")
            rows = rows.sort_values("变更日期")

        latest = rows.iloc[-1]
        industry = str(latest.get("行业门类", "")).strip()
        if not industry or industry.lower() == "nan":
            return None
        return {
            "industry": industry,
            "industry_code": str(latest.get("行业编码", "")).strip(),
            "matched_name": str(latest.get("新证券简称", "")).strip(),
            "source": "AkShare stock_industry_change_cninfo / 申银万国行业分类标准",
        }

    if last_error is not None:
        raise last_error
    return None


def fill_missing_with_cninfo(mapping: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """对未匹配股票使用巨潮申万行业分类兜底。"""

    result = mapping.copy()
    errors: list[str] = []
    missing_mask = result["industry"] == "未识别"

    for index, row in result[missing_mask].iterrows():
        symbol = normalize_symbol(row["symbol"])
        try:
            fallback = fetch_cninfo_sw_industry(symbol)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{symbol} {row['name']} cninfo fallback: {exc}")
            continue

        if not fallback:
            errors.append(f"{symbol} {row['name']} cninfo fallback: 未找到申万分类记录")
            continue

        for column, value in fallback.items():
            result.at[index, column] = value

    return result, errors


def build_industry_mapping(top_pool_path: Path, output_path: Path, top_n: int) -> pd.DataFrame:
    """生成并写出行业映射表。"""

    targets = load_target_stocks(top_pool_path, top_n)
    industries = fetch_sw_first_industries()
    mapping, errors = find_industry_for_targets(targets, industries)
    mapping, fallback_errors = fill_missing_with_cninfo(mapping)
    errors.extend(fallback_errors)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(output_path, index=False, encoding="utf-8-sig")
    if errors:
        error_path = output_path.with_name("industry_mapping_errors.csv")
        pd.DataFrame({"error": errors}).to_csv(error_path, index=False, encoding="utf-8-sig")
    return mapping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-pool", type=Path, default=DEFAULT_TOP_POOL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--top-n", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mapping = build_industry_mapping(
        top_pool_path=args.top_pool,
        output_path=args.output,
        top_n=args.top_n,
    )

    print(f"申万一级行业映射生成完成：{args.output}")
    print(mapping.to_string(index=False))

    missing = mapping[mapping["industry"] == "未识别"]
    if not missing.empty:
        print("\n未匹配到申万一级行业的股票：")
        print(missing[["symbol", "name"]].to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
