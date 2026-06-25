"""第4周 4.2：生成 A股因子库原始因子表。

当前版本做 9 个因子，暂时跳过北向资金：

行情因子：
- momentum_20d：过去20个交易日涨跌幅
- turnover_change：近5日均换手率 / 近20日均换手率 - 1
- volatility_60d：近60日收益率年化波动率

估值因子：
- pe_percentile：当前PE在近五年PE序列里的分位
- pb_percentile：当前PB在近五年PB序列里的分位

财务因子：
- roe：净资产收益率
- gross_margin：毛利率
- revenue_growth_yoy：营业收入同比增长率
- net_profit_growth_yoy：净利润同比增长率
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

import pandas as pd

# 复用第二周已经写好的数据获取函数。这里把 week2 加到 sys.path，
# 这样运行 `python week4/factor_ranking.py` 时也能找到 data_fetcher.py。
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "week2"))

import akshare as ak  # noqa: E402
from data_fetcher import get_daily_data, get_financial_data  # noqa: E402
from factors import (  # noqa: E402
    calc_gross_margin,
    calc_momentum,
    calc_net_profit_growth_yoy,
    calc_pb_percentile,
    calc_pe_percentile,
    calc_revenue_growth_yoy,
    calc_roe,
    calc_turnover_change,
    calc_volatility,
)


DEFAULT_START_DATE = "20260101"
DEFAULT_END_DATE = "20260623"
DEFAULT_UNIVERSE_PATH = ROOT / "week4/data/stock_universe.csv"
DEFAULT_OUTPUT_PATH = ROOT / "week4/data/factor_raw.csv"
DEFAULT_ERROR_PATH = ROOT / "week4/data/factor_errors.csv"
DEFAULT_CACHE_DIR = ROOT / "week4/data/cache"
ERROR_COLUMNS = ["symbol", "name", "industry", "error_type", "error_message"]


def _cache_name(symbol: str, data_type: str, extra: str = "") -> str:
    """生成稳定的缓存文件名。

    沪深300批量跑时，每只股票至少要请求日线、财务、PE、PB 四份数据。
    缓存之后，第二次运行就能直接读本地 CSV，不用重复请求接口。
    """

    suffix = f"_{extra}" if extra else ""
    safe_extra = suffix.replace("(", "").replace(")", "").replace("/", "_")
    return f"{data_type}_{symbol}{safe_extra}.csv"


def cached_frame(
    cache_dir: Path,
    symbol: str,
    data_type: str,
    fetcher: Callable[[], pd.DataFrame],
    *,
    extra: str = "",
    refresh: bool = False,
) -> pd.DataFrame:
    """读取或写入单只股票的数据缓存。"""

    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / _cache_name(symbol, data_type, extra)
    if path.exists() and not refresh:
        return pd.read_csv(path)

    frame = fetcher()
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return frame


def get_valuation_series(
    symbol: str,
    indicator: str,
    period: str = "近五年",
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> pd.Series:
    """获取个股历史估值序列。

    AkShare 的 `stock_zh_valuation_baidu` 返回两列：
    - date：日期
    - value：估值数值

    我们只需要 value 序列来计算当前 PE/PB 在近五年中的分位数。
    """

    frame = cached_frame(
        cache_dir,
        symbol,
        data_type="valuation",
        extra=indicator,
        refresh=refresh,
        fetcher=lambda: ak.stock_zh_valuation_baidu(
            symbol=symbol,
            indicator=indicator,
            period=period,
        ),
    )
    if "value" not in frame.columns:
        raise ValueError(f"{symbol} {indicator} 估值数据缺少 value 字段。")
    return pd.to_numeric(frame["value"], errors="coerce")


def calculate_stock_factors(
    symbol: str,
    name: str,
    industry: str,
    start_date: str,
    end_date: str,
    cache_dir: Path,
    refresh: bool,
) -> dict[str, object]:
    """计算单只股票的 9 个原始因子。

    这里故意不做 Z-score，也不做综合分。4.2 的目标是先把“原始因子库”
    建起来；标准化和加权排名属于 4.3。
    """

    # 1. 日线行情：用于动量、换手率变化、波动率。
    daily = cached_frame(
        cache_dir,
        symbol,
        data_type="daily",
        extra=f"{start_date}_{end_date}_qfq",
        refresh=refresh,
        fetcher=lambda: get_daily_data(symbol, start_date, end_date, adjust="qfq"),
    )

    # 2. 财务摘要：用于 ROE、毛利率、营收增长、净利润增长。
    financial = cached_frame(
        cache_dir,
        symbol,
        data_type="financial",
        refresh=refresh,
        fetcher=lambda: get_financial_data(symbol),
    )

    # 3. 历史估值：用于 PE/PB 近五年分位数。
    pe_series = get_valuation_series(
        symbol,
        indicator="市盈率(TTM)",
        cache_dir=cache_dir,
        refresh=refresh,
    )
    pb_series = get_valuation_series(
        symbol,
        indicator="市净率",
        cache_dir=cache_dir,
        refresh=refresh,
    )

    return {
        "symbol": symbol,
        "name": name,
        "industry": industry,
        "momentum_20d": calc_momentum(daily, window=20),
        "turnover_change": calc_turnover_change(daily, short_window=5, long_window=20),
        "pe_percentile": calc_pe_percentile(pe_series),
        "pb_percentile": calc_pb_percentile(pb_series),
        "roe": calc_roe(financial),
        "gross_margin": calc_gross_margin(financial),
        "revenue_growth_yoy": calc_revenue_growth_yoy(financial),
        "net_profit_growth_yoy": calc_net_profit_growth_yoy(financial),
        "volatility_60d": calc_volatility(daily, window=60),
    }


def build_factor_table(
    universe_path: Path,
    start_date: str,
    end_date: str,
    cache_dir: Path,
    refresh: bool,
    resume_from: Path | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """循环股票池，生成因子表和错误表。

    某只股票失败时不中断整个流程，而是写入 errors。
    这样可以一眼看出到底是哪个接口、哪只股票出了问题。
    """

    universe = pd.read_csv(universe_path, dtype={"symbol": str})
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
        symbol = stock["symbol"]
        name = stock["name"]
        industry = stock.get("industry", "unknown")
        if symbol in completed_symbols:
            print(f"跳过已完成：{symbol} {name}")
            continue
        print(f"计算因子：{symbol} {name}")

        try:
            row = calculate_stock_factors(
                symbol=symbol,
                name=name,
                industry=industry,
                start_date=start_date,
                end_date=end_date,
                cache_dir=cache_dir,
                refresh=refresh,
            )
            rows.append(row)
            print(f"  OK：{symbol} {name}")
        except Exception as exc:  # noqa: BLE001 - 批量验证时需要继续跑后面的股票
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
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--errors", type=Path, default=DEFAULT_ERROR_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="忽略本地缓存，重新请求所有数据。",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="如果输出文件已存在，跳过已经算过的股票，适合沪深300中途断点续跑。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    factor_table, error_table = build_factor_table(
        universe_path=args.universe,
        start_date=args.start_date,
        end_date=args.end_date,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        resume_from=args.output if args.resume else None,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    factor_table.to_csv(args.output, index=False, encoding="utf-8-sig")
    error_table.to_csv(args.errors, index=False, encoding="utf-8-sig")

    print("\n输出完成")
    print(f"因子表：{args.output}，共 {len(factor_table)} 行")
    print(f"错误表：{args.errors}，共 {len(error_table)} 行")
    return 0 if error_table.empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
