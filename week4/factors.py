"""第4周 A股因子库。


分工：
- 行情因子：读取日线行情，比如动量、换手率变化、波动率；
- 估值因子：读取历史 PE/PB 序列，计算当前估值分位；
- 财务因子：读取 AkShare 财务摘要宽表，比如 ROE、毛利率、增长率；
- 得分工具：给后面的多因子排名做 Z-score 标准化。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FactorMeta:
    """因子说明。

    direction 用来表示方向：
    - 1 表示越高越好，比如动量、ROE；
    - -1 表示越低越好，比如 PE 分位数、波动率。
    """

    name: str
    category: str
    direction: int
    data_source: str
    description: str


FACTOR_LIBRARY: dict[str, FactorMeta] = {
    "momentum_20d": FactorMeta(
        name="月度动量",
        category="动量",
        direction=1,
        data_source="日线行情",
        description="过去20个交易日涨跌幅，越高说明近期走势越强。",
    ),
    "turnover_change": FactorMeta(
        name="换手率变化",
        category="动量",
        direction=1,
        data_source="日线行情",
        description="近5日平均换手率相对近20日平均换手率的变化。",
    ),
    "pe_percentile": FactorMeta(
        name="PE分位数",
        category="价值",
        direction=-1,
        data_source="估值/财务数据",
        description="当前PE在历史PE中的分位，越低通常越便宜。",
    ),
    "pb_percentile": FactorMeta(
        name="PB分位数",
        category="价值",
        direction=-1,
        data_source="估值/财务数据",
        description="当前PB在历史PB中的分位，越低通常越便宜。",
    ),
    "roe": FactorMeta(
        name="ROE",
        category="质量",
        direction=1,
        data_source="财务数据",
        description="净资产收益率，衡量公司用股东权益赚钱的能力。",
    ),
    "gross_margin": FactorMeta(
        name="毛利率",
        category="质量",
        direction=1,
        data_source="财务数据",
        description="毛利润占营业收入比例，反映业务盈利空间。",
    ),
    "revenue_growth_yoy": FactorMeta(
        name="营收增长率",
        category="成长",
        direction=1,
        data_source="财务数据",
        description="营业收入同比增长率。",
    ),
    "net_profit_growth_yoy": FactorMeta(
        name="净利润增长率",
        category="成长",
        direction=1,
        data_source="财务数据",
        description="净利润同比增长率。",
    ),
    "volatility_60d": FactorMeta(
        name="60日波动率",
        category="波动",
        direction=-1,
        data_source="日线行情",
        description="近60日收益率标准差，越低说明短期波动越小。",
    ),
    "northbound_holding_change": FactorMeta(
        name="北向持仓变化",
        category="资金",
        direction=1,
        data_source="北向资金数据",
        description="北向资金持仓或持股市值变化，越高说明资金更偏流入。",
    ),
}


def _sorted_daily_data(df: pd.DataFrame, required: Iterable[str]) -> pd.DataFrame:
    """把日线数据按日期排好，并检查计算因子需要的字段。"""

    required_columns = {"date", *required}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"日线数据缺少必要字段：{sorted(missing_columns)}")

    result = df.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for column in required:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=["date", *required])
    return result.sort_values("date").reset_index(drop=True)


def _safe_divide(numerator: float, denominator: float, label: str) -> float:
    """做除法前先挡住空值和 0 分母，避免静默算出无意义结果。"""

    if pd.isna(numerator) or pd.isna(denominator):
        raise ValueError(f"{label} 含空值，无法计算。")
    if denominator == 0:
        raise ValueError(f"{label} 的分母为 0，无法计算。")
    return float(numerator / denominator)


def calc_momentum(df: pd.DataFrame, window: int = 20) -> float:
    """计算动量因子。

    公式：
        最新收盘价 / N 个交易日前收盘价 - 1

    例子：
        20 个交易日前是 100 元，现在是 110 元，动量就是 10%。
    """

    if window <= 0:
        raise ValueError("window 必须大于 0。")
    daily = _sorted_daily_data(df, required=["close"])
    if len(daily) <= window:
        raise ValueError(f"数据不足：计算 {window} 日动量至少需要 {window + 1} 条日线。")

    ratio = _safe_divide(
        daily["close"].iloc[-1],
        daily["close"].iloc[-window - 1],
        f"{window}日动量",
    )
    return ratio - 1


def calc_turnover_change(
    df: pd.DataFrame,
    short_window: int = 5,
    long_window: int = 20,
    turnover_column: str | None = None,
) -> float:
    """计算换手率变化。

    公式：
        近5日平均换手率 / 近20日平均换手率 - 1

    含义：
        看最近交易热度是否比过去一个月明显升温。
    """

    if short_window <= 0 or long_window <= 0:
        raise ValueError("short_window 和 long_window 必须大于 0。")
    if short_window > long_window:
        raise ValueError("short_window 不应大于 long_window。")

    column = turnover_column or _first_existing_column(
        df, ["turnover", "turnover_pct", "换手率"]
    )
    daily = _sorted_daily_data(df, required=[column])
    if len(daily) < long_window:
        raise ValueError(f"数据不足：计算换手率变化至少需要 {long_window} 条日线。")

    short_mean = daily[column].tail(short_window).mean()
    long_mean = daily[column].tail(long_window).mean()
    return _safe_divide(short_mean, long_mean, "换手率变化") - 1


def calc_volatility(df: pd.DataFrame, window: int = 60, annualize: bool = True) -> float:
    """计算收益率波动率。

    默认做年化处理：日收益率标准差 * sqrt(252)。
    波动率通常是反向因子，越低说明短期价格越稳。
    """

    if window <= 1:
        raise ValueError("window 必须大于 1。")
    daily = _sorted_daily_data(df, required=["close"])
    if len(daily) <= window:
        raise ValueError(f"数据不足：计算 {window} 日波动率至少需要 {window + 1} 条日线。")

    returns = daily["close"].pct_change(fill_method=None).dropna().tail(window)
    volatility = returns.std()
    if annualize:
        volatility *= np.sqrt(252)
    return float(volatility)


def calc_percentile(series: pd.Series, current_value: float | None = None) -> float:
    """计算当前值在历史序列里的分位数。

    返回值在 0 到 1 之间。比如 0.8 表示当前值高于或等于历史上
    80% 的样本。PE/PB 分位数越低，通常说明估值越便宜。
    """

    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        raise ValueError("历史序列为空，无法计算分位数。")
    current = values.iloc[-1] if current_value is None else float(current_value)
    return float((values <= current).mean())


def calc_pe_percentile(pe_series: pd.Series) -> float:
    """计算当前 PE 在历史 PE 序列中的分位数。"""

    return calc_percentile(pe_series)


def calc_pb_percentile(pb_series: pd.Series) -> float:
    """计算当前 PB 在历史 PB 序列中的分位数。"""

    return calc_percentile(pb_series)


def calc_roe(financial_df: pd.DataFrame) -> float:
    """从财务摘要表里取最新 ROE。

    AkShare 财务摘要通常已经把 ROE 表示成百分数，比如 12.3 表示 12.3%。
    """

    return _latest_metric_value(
        financial_df,
        ["净资产收益率", "ROE", "加权净资产收益率", "净资产收益率ROE"],
    )


def calc_gross_margin(financial_df: pd.DataFrame) -> float:
    """取最新毛利率；如果没有毛利率字段，就用收入和成本反算。"""

    try:
        return _latest_metric_value(
            financial_df,
            ["销售毛利率", "毛利率", "营业毛利率", "销售毛利率(%)"],
        )
    except ValueError:
        revenue = _latest_metric_value(financial_df, ["营业总收入", "营业收入"])
        cost = _latest_metric_value(financial_df, ["营业成本", "营业总成本"])
        return 1 - _safe_divide(cost, revenue, "毛利率")


def calc_revenue_growth_yoy(financial_df: pd.DataFrame) -> float:
    """计算最新一期营业收入同比增长率。"""

    return _yoy_growth(financial_df, ["营业总收入", "营业收入"])


def calc_net_profit_growth_yoy(financial_df: pd.DataFrame) -> float:
    """计算最新一期净利润同比增长率。"""

    return _yoy_growth(financial_df, ["净利润", "归母净利润", "归属于母公司所有者的净利润"])


def calc_northbound_holding_change(
    northbound_df: pd.DataFrame,
    window: int = 20,
    value_column: str | None = None,
) -> float:
    """计算北向持仓变化。

    先跳过北向资金
    """

    if window <= 0:
        raise ValueError("window 必须大于 0。")
    column = value_column or _first_existing_column(
        northbound_df,
        ["持股市值", "持股数量", "northbound_holding", "holding_value"],
    )
    flow = _sorted_daily_data(northbound_df, required=[column])
    if len(flow) <= window:
        raise ValueError(f"数据不足：计算北向持仓变化至少需要 {window + 1} 条记录。")

    ratio = _safe_divide(flow[column].iloc[-1], flow[column].iloc[-window - 1], "北向持仓变化")
    return ratio - 1


def zscore(series: pd.Series) -> pd.Series:
    """Z-score 标准化，让不同单位的因子变得可比较。"""

    values = pd.to_numeric(series, errors="coerce")
    std = values.std()
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (values - values.mean()) / std


def direction_adjusted_zscore(series: pd.Series, direction: int) -> pd.Series:
    """标准化并统一方向，让处理后的分数永远是越高越好。"""

    if direction not in {1, -1}:
        raise ValueError("direction 只能是 1 或 -1。")
    return zscore(series) * direction


def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str:
    for column in candidates:
        if column in df.columns:
            return column
    raise ValueError(f"找不到可用字段，候选字段：{candidates}")


def _period_columns(financial_df: pd.DataFrame) -> list[str]:
    columns = [column for column in financial_df.columns if str(column).isdigit()]
    return sorted(columns, reverse=True)


def _metric_row(financial_df: pd.DataFrame, metric_names: list[str]) -> pd.Series:
    if "指标" not in financial_df.columns:
        raise ValueError("财务数据缺少“指标”列，无法按指标名称取数。")

    metric_text = financial_df["指标"].astype(str)
    for metric_name in metric_names:
        matched = financial_df[metric_text.str.contains(metric_name, regex=False, na=False)]
        if not matched.empty:
            return matched.iloc[0]
    raise ValueError(f"财务数据找不到指标：{metric_names}")


def _latest_metric_value(financial_df: pd.DataFrame, metric_names: list[str]) -> float:
    row = _metric_row(financial_df, metric_names)
    for period in _period_columns(financial_df):
        value = pd.to_numeric(row[period], errors="coerce")
        if pd.notna(value):
            return float(value)
    raise ValueError(f"指标没有可用数值：{metric_names}")


def _yoy_growth(financial_df: pd.DataFrame, metric_names: list[str]) -> float:
    row = _metric_row(financial_df, metric_names)
    periods = _period_columns(financial_df)
    for period in periods:
        previous_year_period = str(int(period[:4]) - 1) + period[4:]
        if previous_year_period not in financial_df.columns:
            continue
        current_value = pd.to_numeric(row[period], errors="coerce")
        previous_value = pd.to_numeric(row[previous_year_period], errors="coerce")
        if pd.notna(current_value) and pd.notna(previous_value):
            return _safe_divide(current_value, previous_value, f"{metric_names[0]}同比增长") - 1
    raise ValueError(f"找不到可用于同比计算的报告期：{metric_names}")


__all__ = [
    "FACTOR_LIBRARY",
    "FactorMeta",
    "calc_gross_margin",
    "calc_momentum",
    "calc_net_profit_growth_yoy",
    "calc_northbound_holding_change",
    "calc_pb_percentile",
    "calc_pe_percentile",
    "calc_percentile",
    "calc_revenue_growth_yoy",
    "calc_roe",
    "calc_turnover_change",
    "calc_volatility",
    "direction_adjusted_zscore",
    "zscore",
]
