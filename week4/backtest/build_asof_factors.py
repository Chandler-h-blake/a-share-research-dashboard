"""Build strict as-of factor snapshots for Week 4 factor backtests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "week2"))
sys.path.insert(0, str(ROOT / "week4"))

from data_fetcher import get_daily_data, get_financial_data  # noqa: E402
from factors import (  # noqa: E402
    calc_momentum,
    calc_pb_percentile,
    calc_pe_percentile,
    calc_turnover_change,
    calc_volatility,
)


DEFAULT_ASOF_DATE = "20260520"
DEFAULT_START_DATE = "20260101"
DEFAULT_UNIVERSE_PATH = ROOT / "week4/data/hs300_universe.csv"
DEFAULT_CACHE_DIR = ROOT / "week4/data/cache"
DEFAULT_DISCLOSURE_PATH = ROOT / "week4/data/backtest/disclosure_calendar.csv"
DEFAULT_OUTPUT_PATH = ROOT / "week4/data/backtest/factor_raw_20260520.csv"
DEFAULT_ERROR_PATH = ROOT / "week4/data/backtest/factor_errors_20260520.csv"
ERROR_COLUMNS = ["symbol", "name", "industry", "error_type", "error_message"]


def _cache_name(symbol: str, data_type: str, extra: str = "") -> str:
    suffix = f"_{extra}" if extra else ""
    safe_extra = suffix.replace("(", "").replace(")", "").replace("/", "_")
    return f"{data_type}_{symbol}{safe_extra}.csv"


def _read_or_fetch_daily(
    symbol: str,
    start_date: str,
    asof_date: str,
    cache_dir: Path,
    refresh: bool,
) -> pd.DataFrame:
    exact = cache_dir / _cache_name(symbol, "daily", f"{start_date}_{asof_date}_qfq")
    if exact.exists() and not refresh:
        return pd.read_csv(exact)

    for path in sorted(cache_dir.glob(f"daily_{symbol}_*_qfq.csv")):
        frame = pd.read_csv(path)
        if "date" not in frame.columns:
            continue
        dates = pd.to_datetime(frame["date"], errors="coerce")
        if dates.min() <= pd.to_datetime(start_date) and dates.max() >= pd.to_datetime(asof_date):
            return frame

    frame = get_daily_data(symbol, start_date, asof_date, adjust="qfq")
    exact.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(exact, index=False, encoding="utf-8-sig")
    return frame


def _read_or_fetch_financial(symbol: str, cache_dir: Path, refresh: bool) -> pd.DataFrame:
    path = cache_dir / _cache_name(symbol, "financial")
    if path.exists() and not refresh:
        return pd.read_csv(path)

    frame = get_financial_data(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return frame


def _read_valuation(symbol: str, indicator: str, cache_dir: Path) -> pd.DataFrame:
    path = cache_dir / _cache_name(symbol, "valuation", indicator)
    if not path.exists():
        raise FileNotFoundError(f"缺少估值缓存：{path}")
    frame = pd.read_csv(path)
    if not {"date", "value"}.issubset(frame.columns):
        raise ValueError(f"估值缓存字段不完整：{path}")
    return frame


def _truncate_daily(daily: pd.DataFrame, asof_date: str) -> tuple[pd.DataFrame, str]:
    result = daily.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result = result[result["date"] <= pd.to_datetime(asof_date)].dropna(subset=["date"])
    if result.empty:
        raise ValueError(f"截至 {asof_date} 没有可用日线数据。")
    return result, result["date"].max().strftime("%Y-%m-%d")


def _valuation_percentile_asof(frame: pd.DataFrame, asof_date: str, label: str) -> float:
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    result = result[result["date"] <= pd.to_datetime(asof_date)].dropna(subset=["date", "value"])
    result = result.sort_values("date")
    if result.empty:
        raise ValueError(f"截至 {asof_date} 没有可用{label}估值数据。")
    if label == "PE":
        return calc_pe_percentile(result["value"])
    return calc_pb_percentile(result["value"])


def _period_columns(financial: pd.DataFrame) -> set[str]:
    return {str(column) for column in financial.columns if str(column).isdigit()}


def _metric_row(financial: pd.DataFrame, metric_names: list[str]) -> pd.Series:
    if "指标" not in financial.columns:
        raise ValueError("财务数据缺少“指标”列。")
    metric_text = financial["指标"].astype(str)
    for metric_name in metric_names:
        matched = financial[metric_text.str.contains(metric_name, regex=False, na=False)]
        if not matched.empty:
            return matched.iloc[0]
    raise ValueError(f"财务数据找不到指标：{metric_names}")


def _metric_at_period(financial: pd.DataFrame, metric_names: list[str], period: str) -> float:
    if period not in financial.columns:
        raise ValueError(f"财务数据缺少报告期列：{period}")
    row = _metric_row(financial, metric_names)
    value = pd.to_numeric(row[period], errors="coerce")
    if pd.isna(value):
        raise ValueError(f"指标 {metric_names} 在 {period} 没有可用数值。")
    return float(value)


def _safe_divide(numerator: float, denominator: float, label: str) -> float:
    if pd.isna(numerator) or pd.isna(denominator):
        raise ValueError(f"{label} 含空值，无法计算。")
    if denominator == 0:
        raise ValueError(f"{label} 分母为 0，无法计算。")
    return float(numerator / denominator)


def _growth_yoy_at_period(
    financial: pd.DataFrame,
    metric_names: list[str],
    period: str,
) -> float:
    previous_period = str(int(period[:4]) - 1) + period[4:]
    current_value = _metric_at_period(financial, metric_names, period)
    previous_value = _metric_at_period(financial, metric_names, previous_period)
    return _safe_divide(current_value, previous_value, f"{metric_names[0]}同比增长") - 1


def _gross_margin_at_period(financial: pd.DataFrame, period: str) -> float:
    try:
        return _metric_at_period(financial, ["销售毛利率", "毛利率", "营业毛利率", "销售毛利率(%)"], period)
    except ValueError:
        revenue = _metric_at_period(financial, ["营业总收入", "营业收入"], period)
        cost = _metric_at_period(financial, ["营业成本", "营业总成本"], period)
        return 1 - _safe_divide(cost, revenue, "毛利率")


def _latest_report_period_asof(
    disclosure: pd.DataFrame,
    financial: pd.DataFrame,
    symbol: str,
    asof_date: str,
) -> tuple[str, str]:
    available_periods = _period_columns(financial)
    rows = disclosure[disclosure["symbol"].astype(str) == symbol].copy()
    if rows.empty:
        raise ValueError("披露日历缺少该股票记录。")

    rows["announcement_date"] = pd.to_datetime(rows["announcement_date"], errors="coerce")
    rows["report_period"] = rows["report_period"].astype(str)
    rows = rows[
        (rows["announcement_date"] <= pd.to_datetime(asof_date))
        & rows["report_period"].isin(available_periods)
    ].dropna(subset=["announcement_date"])
    if rows.empty:
        raise ValueError(f"截至 {asof_date} 没有已公告且可计算的财报。")

    rows = rows.sort_values(["report_period", "announcement_date"], ascending=[False, False])
    row = rows.iloc[0]
    return str(row["report_period"]), row["announcement_date"].strftime("%Y-%m-%d")


def _ensure_previous_period_disclosed(
    disclosure: pd.DataFrame,
    symbol: str,
    period: str,
    asof_date: str,
) -> None:
    previous_period = str(int(period[:4]) - 1) + period[4:]
    rows = disclosure[disclosure["symbol"].astype(str) == symbol].copy()
    rows["announcement_date"] = pd.to_datetime(rows["announcement_date"], errors="coerce")
    rows["report_period"] = rows["report_period"].astype(str)
    matched = rows[
        (rows["report_period"] == previous_period)
        & (rows["announcement_date"] <= pd.to_datetime(asof_date))
    ]
    if matched.empty:
        raise ValueError(f"同比计算所需上一年同期 {previous_period} 未在截面日前公告。")


def calculate_stock_factors_asof(
    symbol: str,
    name: str,
    industry: str,
    start_date: str,
    asof_date: str,
    cache_dir: Path,
    disclosure: pd.DataFrame,
    refresh: bool,
) -> dict[str, object]:
    daily = _read_or_fetch_daily(symbol, start_date, asof_date, cache_dir, refresh)
    daily_asof, price_asof_date = _truncate_daily(daily, asof_date)

    financial = _read_or_fetch_financial(symbol, cache_dir, refresh)
    report_period, report_announcement_date = _latest_report_period_asof(
        disclosure,
        financial,
        symbol,
        asof_date,
    )
    _ensure_previous_period_disclosed(disclosure, symbol, report_period, asof_date)

    pe = _read_valuation(symbol, "市盈率(TTM)", cache_dir)
    pb = _read_valuation(symbol, "市净率", cache_dir)

    return {
        "symbol": symbol,
        "name": name,
        "industry": industry,
        "asof_date": asof_date,
        "price_asof_date": price_asof_date,
        "financial_report_period": report_period,
        "financial_announcement_date": report_announcement_date,
        "momentum_20d": calc_momentum(daily_asof, window=20),
        "turnover_change": calc_turnover_change(daily_asof, short_window=5, long_window=20),
        "pe_percentile": _valuation_percentile_asof(pe, asof_date, "PE"),
        "pb_percentile": _valuation_percentile_asof(pb, asof_date, "PB"),
        "roe": _metric_at_period(
            financial,
            ["净资产收益率", "ROE", "加权净资产收益率", "净资产收益率ROE"],
            report_period,
        ),
        "gross_margin": _gross_margin_at_period(financial, report_period),
        "revenue_growth_yoy": _growth_yoy_at_period(financial, ["营业总收入", "营业收入"], report_period),
        "net_profit_growth_yoy": _growth_yoy_at_period(
            financial,
            ["净利润", "归母净利润", "归属于母公司所有者的净利润"],
            report_period,
        ),
        "volatility_60d": calc_volatility(daily_asof, window=60),
    }


def build_factor_table_asof(
    universe_path: Path,
    disclosure_path: Path,
    start_date: str,
    asof_date: str,
    cache_dir: Path,
    refresh: bool,
    resume_from: Path | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not disclosure_path.exists():
        raise FileNotFoundError(f"缺少披露日历：{disclosure_path}")

    universe = pd.read_csv(universe_path, dtype={"symbol": str})
    disclosure = pd.read_csv(disclosure_path, dtype={"symbol": str, "report_period": str})
    rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    completed_symbols: set[str] = set()

    if resume_from and resume_from.exists() and not refresh:
        existing = pd.read_csv(resume_from, dtype={"symbol": str})
        if not existing.empty and "symbol" in existing.columns:
            rows.extend(existing.to_dict("records"))
            completed_symbols = set(existing["symbol"].astype(str))
            print(f"断点续跑：已读取 {len(completed_symbols)} 只已完成股票。")

    for _, stock in universe.iterrows():
        symbol = str(stock["symbol"])
        name = str(stock.get("name", ""))
        industry = str(stock.get("industry", "unknown"))
        if symbol in completed_symbols:
            print(f"跳过已完成：{symbol} {name}")
            continue

        print(f"计算严格截面因子：{symbol} {name}")
        try:
            row = calculate_stock_factors_asof(
                symbol=symbol,
                name=name,
                industry=industry,
                start_date=start_date,
                asof_date=asof_date,
                cache_dir=cache_dir,
                disclosure=disclosure,
                refresh=refresh,
            )
            rows.append(row)
            print(f"  OK：{symbol} {name}")
        except Exception as exc:  # noqa: BLE001 - 批量计算需要继续
            errors.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "industry": industry,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            print(f"  FAIL：{symbol} {name} -> {type(exc).__name__}: {exc}")

    return pd.DataFrame(rows), pd.DataFrame(errors, columns=ERROR_COLUMNS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asof-date", default=DEFAULT_ASOF_DATE)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--disclosure-calendar", type=Path, default=DEFAULT_DISCLOSURE_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--errors", type=Path, default=DEFAULT_ERROR_PATH)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    factor_table, error_table = build_factor_table_asof(
        universe_path=args.universe,
        disclosure_path=args.disclosure_calendar,
        start_date=args.start_date,
        asof_date=args.asof_date,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        resume_from=args.output if args.resume else None,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    factor_table.to_csv(args.output, index=False, encoding="utf-8-sig")
    error_table.to_csv(args.errors, index=False, encoding="utf-8-sig")

    print("\n输出完成")
    print(f"严格截面因子表：{args.output}，共 {len(factor_table)} 行")
    print(f"错误表：{args.errors}，共 {len(error_table)} 行")
    return 0 if error_table.empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
