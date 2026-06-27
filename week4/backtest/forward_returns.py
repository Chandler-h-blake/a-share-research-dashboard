"""Calculate forward returns after a strict factor snapshot date."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FACTOR_PATH = ROOT / "week4/data/backtest/factor_raw_20260520.csv"
DEFAULT_CACHE_DIR = ROOT / "week4/data/cache"
DEFAULT_OUTPUT_PATH = ROOT / "week4/data/backtest/forward_returns_20260520_20d.csv"
DEFAULT_ERROR_PATH = ROOT / "week4/data/backtest/forward_return_errors_20260520_20d.csv"
ERROR_COLUMNS = ["symbol", "name", "error_type", "error_message"]


def _load_daily_from_cache(symbol: str, cache_dir: Path) -> pd.DataFrame:
    """Load a cached daily file that covers the backtest period."""

    candidates = sorted(cache_dir.glob(f"daily_{symbol}_*_qfq.csv"))
    if not candidates:
        raise FileNotFoundError(f"找不到日线缓存：{symbol}")

    best_frame: pd.DataFrame | None = None
    best_length = -1
    for path in candidates:
        frame = pd.read_csv(path)
        if "date" not in frame.columns or "close" not in frame.columns:
            continue
        length = len(frame)
        if length > best_length:
            best_frame = frame
            best_length = length

    if best_frame is None:
        raise ValueError(f"日线缓存缺少 date/close 字段：{symbol}")
    return best_frame


def calculate_forward_return(
    daily: pd.DataFrame,
    price_asof_date: str,
    holding_days: int,
) -> dict[str, object]:
    """Calculate close-to-close return after N trading days."""

    if holding_days <= 0:
        raise ValueError("holding_days 必须大于 0。")

    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)

    asof_ts = pd.to_datetime(price_asof_date)
    matches = frame.index[frame["date"] == asof_ts].tolist()
    if not matches:
        raise ValueError(f"日线数据中找不到截面交易日：{price_asof_date}")

    asof_index = matches[-1]
    future_index = asof_index + holding_days
    if future_index >= len(frame):
        raise ValueError(f"截面日后不足 {holding_days} 个交易日。")

    asof_close = float(frame.loc[asof_index, "close"])
    future_close = float(frame.loc[future_index, "close"])
    if asof_close == 0:
        raise ValueError("截面日收盘价为 0，无法计算收益。")

    return {
        "price_asof_date": frame.loc[asof_index, "date"].strftime("%Y-%m-%d"),
        "asof_close": asof_close,
        "future_date": frame.loc[future_index, "date"].strftime("%Y-%m-%d"),
        "future_close": future_close,
        f"forward_return_{holding_days}d": future_close / asof_close - 1,
    }


def build_forward_returns(
    factor_path: Path,
    cache_dir: Path,
    holding_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    factors = pd.read_csv(factor_path, dtype={"symbol": str})
    rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []

    for _, stock in factors.iterrows():
        symbol = str(stock["symbol"])
        name = str(stock.get("name", ""))
        print(f"计算未来收益：{symbol} {name}")
        try:
            daily = _load_daily_from_cache(symbol, cache_dir)
            result = calculate_forward_return(
                daily=daily,
                price_asof_date=str(stock["price_asof_date"]),
                holding_days=holding_days,
            )
            rows.append(
                {
                    "symbol": symbol,
                    "name": name,
                    **result,
                }
            )
            print(f"  OK：{symbol} {name} -> {result['future_date']}")
        except Exception as exc:  # noqa: BLE001 - 批量计算需要继续
            errors.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            print(f"  FAIL：{symbol} {name} -> {type(exc).__name__}: {exc}")

    return pd.DataFrame(rows), pd.DataFrame(errors, columns=ERROR_COLUMNS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factors", type=Path, default=DEFAULT_FACTOR_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--holding-days", type=int, default=20)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--errors", type=Path, default=DEFAULT_ERROR_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    returns, errors = build_forward_returns(
        factor_path=args.factors,
        cache_dir=args.cache_dir,
        holding_days=args.holding_days,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    returns.to_csv(args.output, index=False, encoding="utf-8-sig")
    errors.to_csv(args.errors, index=False, encoding="utf-8-sig")

    print("\n输出完成")
    print(f"未来收益表：{args.output}，共 {len(returns)} 行")
    print(f"错误表：{args.errors}，共 {len(errors)} 行")
    return 0 if errors.empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
