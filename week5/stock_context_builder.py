"""第五周：个股研究材料包构建模块。

本模块负责把第四周的多因子结果整理成统一的 StockContext。
后续各个 Agent 都只读取这个上下文，避免在 Agent 内部重复读文件和解释字段。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOP_POOL_PATH = ROOT / "week4/data/final_top30_stock_pool.csv"
DEFAULT_FACTOR_SCORES_PATH = ROOT / "week4/data/final_factor_scores.csv"
DEFAULT_FACTOR_OVERVIEW_PATH = ROOT / "week4/data/final_factor_overview.csv"
DEFAULT_INDUSTRY_MAPPING_PATH = ROOT / "week5/industry_mapping.csv"
DEFAULT_SENTIMENT_INPUT_DIR = ROOT / "week5/sentiment_inputs"


FACTOR_COLUMNS = [
    "momentum_20d",
    "turnover_change",
    "pe_percentile",
    "pb_percentile",
    "roe",
    "gross_margin",
    "revenue_growth_yoy",
    "net_profit_growth_yoy",
    "volatility_60d",
]

CATEGORY_ORDER = ["成长", "动量", "质量", "价值", "波动"]


@dataclass(frozen=True)
class FactorItem:
    """单个因子的研究材料。"""

    factor: str
    name: str
    category: str
    direction_text: str
    weight: float
    raw_value: float | None
    score: float | None
    weighted_score: float | None
    description: str
    ic: float | None
    group_spread: float | None


@dataclass(frozen=True)
class StockContext:
    """单只股票的标准化研究上下文。"""

    symbol: str
    name: str
    industry: str
    rank: int
    composite_score: float
    factor_items: list[FactorItem]
    category_summary: dict[str, float]
    positive_contributors: list[FactorItem]
    negative_contributors: list[FactorItem]
    warnings: list[str]
    sentiment_records: list[dict[str, str]]


def _read_csv(path: Path, dtype: dict[str, Any] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"找不到数据文件：{path}")
    return pd.read_csv(path, dtype=dtype, encoding="utf-8-sig")


def _to_float(value: Any) -> float | None:
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_industry(value: Any) -> str:
    if pd.isna(value):
        return "未识别"
    text = str(value).strip()
    if not text or text.lower() == "unknown":
        return "未识别"
    return text


def load_industry_mapping(path: Path = DEFAULT_INDUSTRY_MAPPING_PATH) -> dict[str, str]:
    """读取第五周轻量行业映射表。

    第四周 final 文件中的行业字段目前大量为 unknown。为了避免重跑前四周
    数据流程，这里只在第五周补一个小映射表，优先服务 TOP 研报股票。
    """

    if not path.exists():
        return {}

    mapping_df = _read_csv(path, dtype={"symbol": str})
    required_columns = {"symbol", "industry"}
    missing_columns = required_columns - set(mapping_df.columns)
    if missing_columns:
        raise ValueError(f"行业映射表缺少字段：{sorted(missing_columns)}")

    mapping: dict[str, str] = {}
    for _, row in mapping_df.iterrows():
        symbol = str(row["symbol"]).zfill(6)
        industry = _clean_industry(row["industry"])
        if industry != "未识别":
            mapping[symbol] = industry
    return mapping


def resolve_industry(raw_value: Any, symbol: str, industry_mapping: dict[str, str]) -> str:
    """优先使用原始行业；若为 unknown，则使用第五周映射表补充。"""

    raw_industry = _clean_industry(raw_value)
    if raw_industry != "未识别":
        return raw_industry
    return industry_mapping.get(str(symbol).zfill(6), raw_industry)


def load_sentiment_records(
    symbol: str,
    sentiment_input_dir: Path = DEFAULT_SENTIMENT_INPUT_DIR,
    max_records: int = 18,
) -> list[dict[str, str]]:
    """读取市场情绪文本材料。

    情绪抓取脚本会把真实抓取结果和失败留痕都写入 CSV。这里不做情绪
    判断，只把材料原样整理进 StockContext，交给 SentimentAgent 分析。
    """

    path = sentiment_input_dir / f"{str(symbol).zfill(6)}_sentiment_texts.csv"
    if not path.exists():
        return [
            {
                "source": "sentiment_fetcher",
                "title": "",
                "content": "",
                "url": "",
                "publish_time": "",
                "fetch_status": f"missing_file: {path}",
            }
        ]

    records_df = _read_csv(path, dtype={"symbol": str})
    required_columns = {"source", "title", "content", "url", "publish_time", "fetch_status"}
    missing_columns = required_columns - set(records_df.columns)
    if missing_columns:
        raise ValueError(f"情绪文本文件缺少字段：{sorted(missing_columns)}")

    records: list[dict[str, str]] = []
    for _, row in records_df.head(max_records).iterrows():
        records.append(
            {
                "source": str(row.get("source", "")).strip(),
                "title": "" if pd.isna(row.get("title")) else str(row.get("title", "")).strip(),
                "content": "" if pd.isna(row.get("content")) else str(row.get("content", "")).strip(),
                "url": "" if pd.isna(row.get("url")) else str(row.get("url", "")).strip(),
                "publish_time": ""
                if pd.isna(row.get("publish_time"))
                else str(row.get("publish_time", "")).strip(),
                "fetch_status": str(row.get("fetch_status", "")).strip(),
            }
        )
    return records


def load_week4_data(
    top_pool_path: Path = DEFAULT_TOP_POOL_PATH,
    factor_scores_path: Path = DEFAULT_FACTOR_SCORES_PATH,
    factor_overview_path: Path = DEFAULT_FACTOR_OVERVIEW_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """读取第五周需要复用的第四周 final 数据。"""

    top_pool = _read_csv(top_pool_path, dtype={"symbol": str})
    factor_scores = _read_csv(factor_scores_path, dtype={"symbol": str})
    factor_overview = _read_csv(factor_overview_path)

    required_top_columns = {"rank", "symbol", "name", "composite_score"}
    missing_top = required_top_columns - set(top_pool.columns)
    if missing_top:
        raise ValueError(f"TOP股票池缺少字段：{sorted(missing_top)}")

    required_score_columns = {"symbol", "name", "composite_score", "rank"}
    missing_score = required_score_columns - set(factor_scores.columns)
    if missing_score:
        raise ValueError(f"因子得分表缺少字段：{sorted(missing_score)}")

    required_overview_columns = {"factor", "name", "category", "direction_text", "weight"}
    missing_overview = required_overview_columns - set(factor_overview.columns)
    if missing_overview:
        raise ValueError(f"因子概览表缺少字段：{sorted(missing_overview)}")

    return top_pool, factor_scores, factor_overview


def get_top_symbols(top_pool: pd.DataFrame, top_n: int = 5) -> list[str]:
    """从 TOP 股票池中取前 top_n 只股票代码。"""

    top = top_pool.sort_values("rank").head(top_n)
    return [str(symbol).zfill(6) for symbol in top["symbol"].tolist()]


def build_stock_context(
    symbol: str,
    factor_scores: pd.DataFrame,
    factor_overview: pd.DataFrame,
    industry_mapping: dict[str, str] | None = None,
    sentiment_input_dir: Path = DEFAULT_SENTIMENT_INPUT_DIR,
) -> StockContext:
    """为单只股票构建统一研究材料包。"""

    symbol = str(symbol).zfill(6)
    industry_mapping = industry_mapping or {}
    rows = factor_scores[factor_scores["symbol"].astype(str).str.zfill(6) == symbol]
    if rows.empty:
        raise ValueError(f"因子得分表中找不到股票：{symbol}")

    stock = rows.iloc[0]
    overview_by_factor = {
        str(row["factor"]): row.to_dict()
        for _, row in factor_overview.iterrows()
    }

    factor_items: list[FactorItem] = []
    for factor in FACTOR_COLUMNS:
        meta = overview_by_factor.get(factor, {})
        factor_items.append(
            FactorItem(
                factor=factor,
                name=str(meta.get("name", factor)),
                category=str(meta.get("category", "未分类")),
                direction_text=str(meta.get("direction_text", "")),
                weight=_to_float(meta.get("weight")) or 0.0,
                raw_value=_to_float(stock.get(factor)),
                score=_to_float(stock.get(f"{factor}_score")),
                weighted_score=_to_float(stock.get(f"{factor}_weighted_score")),
                description=str(meta.get("description", "")),
                ic=_to_float(meta.get("spearman_ic_adjusted")),
                group_spread=_to_float(meta.get("group1_minus_group5")),
            )
        )

    category_summary: dict[str, float] = {}
    for item in factor_items:
        category_summary[item.category] = category_summary.get(item.category, 0.0) + (
            item.weighted_score or 0.0
        )
    category_summary = {
        category: category_summary[category]
        for category in CATEGORY_ORDER
        if category in category_summary
    } | {
        category: value
        for category, value in category_summary.items()
        if category not in CATEGORY_ORDER
    }

    sorted_items = sorted(
        factor_items,
        key=lambda item: item.weighted_score if item.weighted_score is not None else 0.0,
        reverse=True,
    )
    positive = [item for item in sorted_items if (item.weighted_score or 0.0) > 0][:3]
    negative = [
        item
        for item in sorted(factor_items, key=lambda item: item.weighted_score or 0.0)
        if (item.weighted_score or 0.0) < 0
    ][:3]

    warnings = build_data_warnings(factor_items)

    return StockContext(
        symbol=symbol,
        name=str(stock["name"]),
        industry=resolve_industry(stock.get("industry"), symbol, industry_mapping),
        rank=int(stock["rank"]),
        composite_score=float(stock["composite_score"]),
        factor_items=factor_items,
        category_summary=category_summary,
        positive_contributors=positive,
        negative_contributors=negative,
        warnings=warnings,
        sentiment_records=load_sentiment_records(symbol, sentiment_input_dir),
    )


def build_data_warnings(factor_items: list[FactorItem]) -> list[str]:
    """根据原始因子和分数生成需要 Agent 注意的数据提醒。"""

    warnings: list[str] = []
    by_factor = {item.factor: item for item in factor_items}

    pe = by_factor.get("pe_percentile")
    pb = by_factor.get("pb_percentile")
    volatility = by_factor.get("volatility_60d")
    momentum = by_factor.get("momentum_20d")
    revenue = by_factor.get("revenue_growth_yoy")
    profit = by_factor.get("net_profit_growth_yoy")

    if pe and pe.raw_value is not None and pe.raw_value >= 0.8:
        warnings.append("PE 分位数较高，估值层面需要谨慎解释。")
    if pb and pb.raw_value is not None and pb.raw_value >= 0.8:
        warnings.append("PB 分位数较高，账面估值可能不便宜。")
    if volatility and volatility.raw_value is not None and volatility.raw_value >= 0.65:
        warnings.append("60 日波动率偏高，股价回撤风险需要重点跟踪。")
    if momentum and momentum.raw_value is not None and momentum.raw_value >= 0.5:
        warnings.append("20 日动量很强，需警惕短期交易拥挤和追高风险。")
    if revenue and profit and revenue.raw_value is not None and profit.raw_value is not None:
        if revenue.raw_value > 0.5 and profit.raw_value < 0:
            warnings.append("收入增长与利润增长背离，需要进一步检查盈利质量。")
    if not warnings:
        warnings.append("未触发明显单项数据预警，但仍需结合行业和市场环境复核。")

    return warnings


def build_contexts(top_n: int = 5) -> list[StockContext]:
    """构建 TOP N 股票的研究上下文列表。"""

    top_pool, factor_scores, factor_overview = load_week4_data()
    industry_mapping = load_industry_mapping()
    return [
        build_stock_context(symbol, factor_scores, factor_overview, industry_mapping)
        for symbol in get_top_symbols(top_pool, top_n=top_n)
    ]


def format_percent(value: float | None, digits: int = 2) -> str:
    """把小数格式化为百分比；None 返回 N/A。"""

    if value is None:
        return "N/A"
    return f"{value * 100:.{digits}f}%"


def format_number(value: float | None, digits: int = 2) -> str:
    """格式化数字；None 返回 N/A。"""

    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def context_to_markdown(context: StockContext) -> str:
    """把 StockContext 转成 Markdown，便于人工检查或喂给 LLM。"""

    lines = [
        f"## {context.name}（{context.symbol}）研究材料包",
        "",
        f"- 多因子排名：第 {context.rank} 名",
        f"- 综合得分：{context.composite_score:.4f}",
        f"- 行业：{context.industry}",
        "",
        "### 分类贡献",
        "",
    ]
    for category, value in context.category_summary.items():
        lines.append(f"- {category}：{value:.4f}")

    lines.extend(["", "### 单因子明细", ""])
    lines.append("| 因子 | 类别 | 方向 | 权重 | 原始值 | 加权贡献 |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: |")
    for item in context.factor_items:
        lines.append(
            "| {name} | {category} | {direction} | {weight:.2f} | {raw} | {weighted} |".format(
                name=item.name,
                category=item.category,
                direction=item.direction_text,
                weight=item.weight,
                raw=format_number(item.raw_value, 4),
                weighted=format_number(item.weighted_score, 4),
            )
        )

    lines.extend(["", "### 数据提醒", ""])
    for warning in context.warnings:
        lines.append(f"- {warning}")

    lines.extend(["", "### 市场情绪文本材料", ""])
    if not context.sentiment_records:
        lines.append("- 未读取到市场情绪文本材料。")
    else:
        for index, record in enumerate(context.sentiment_records, start=1):
            title = record.get("title") or "无标题"
            content = record.get("content") or ""
            if len(content) > 180:
                content = content[:180] + "..."
            lines.append(
                f"{index}. 来源：{record.get('source', '')}；"
                f"状态：{record.get('fetch_status', '')}；"
                f"时间：{record.get('publish_time', '') or 'N/A'}；"
                f"标题：{title}"
            )
            if content:
                lines.append(f"   摘要：{content}")
            if record.get("url"):
                lines.append(f"   链接：{record['url']}")

    return "\n".join(lines)


def main() -> int:
    contexts = build_contexts(top_n=5)
    for context in contexts:
        print(context_to_markdown(context))
        print("\n" + "=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
