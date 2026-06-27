"""Build a financial report disclosure calendar for strict factor backtests."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import akshare as ak
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UNIVERSE_PATH = ROOT / "week4/data/hs300_universe.csv"
DEFAULT_OUTPUT_PATH = ROOT / "week4/data/backtest/disclosure_calendar.csv"
DEFAULT_ERROR_PATH = ROOT / "week4/data/backtest/disclosure_calendar_errors.csv"
DEFAULT_START_DATE = "20230101"
DEFAULT_END_DATE = "20260520"
OUTPUT_COLUMNS = [
    "symbol",
    "name",
    "report_period",
    "announcement_date",
    "announcement_title",
    "announcement_url",
]
ERROR_COLUMNS = ["symbol", "name", "error_type", "error_message"]
REPORT_CATEGORIES = ["年报", "半年报", "一季报", "三季报"]
EXCLUDED_TITLE_KEYWORDS = [
    "摘要",
    "延期披露",
    "预约披露",
    "更正",
    "取消",
    "提示性公告",
    "披露时间",
]


REPORT_PATTERNS = [
    (re.compile(r"(?P<year>\d{4})年(?:第一季度|一季度|1季度)报告"), "0331"),
    (re.compile(r"(?P<year>\d{4})年(?:半年度|中期)报告"), "0630"),
    (re.compile(r"(?P<year>\d{4})年(?:第三季度|三季度|3季度)报告"), "0930"),
    (re.compile(r"(?P<year>\d{4})年(?:年度|年)报告"), "1231"),
]


def parse_report_period(title: str) -> str | None:
    """Parse a report period such as 20260331 from a Chinese report title."""

    text = str(title)
    if any(keyword in text for keyword in EXCLUDED_TITLE_KEYWORDS):
        return None
    for pattern, suffix in REPORT_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"{match.group('year')}{suffix}"
    return None


def fetch_symbol_disclosures(
    symbol: str,
    name: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Fetch and normalize report disclosures for one stock."""

    frames = []
    for category in REPORT_CATEGORIES:
        try:
            frame = ak.stock_zh_a_disclosure_report_cninfo(
                symbol=symbol,
                market="沪深京",
                category=category,
                start_date=start_date,
                end_date=end_date,
            )
        except KeyError as exc:
            if "公告标题" in str(exc) or "公告时间" in str(exc):
                continue
            raise
        if not frame.empty:
            frames.append(frame)

    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if raw.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    rows: list[dict[str, object]] = []
    for _, item in raw.iterrows():
        title = str(item.get("公告标题", ""))
        report_period = parse_report_period(title)
        if report_period is None:
            continue

        announcement_date = pd.to_datetime(item.get("公告时间"), errors="coerce")
        if pd.isna(announcement_date):
            continue

        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "report_period": report_period,
                "announcement_date": announcement_date.strftime("%Y-%m-%d"),
                "announcement_title": title,
                "announcement_url": item.get("公告链接", ""),
            }
        )

    result = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if result.empty:
        return result
    return (
        result.sort_values(["report_period", "announcement_date"])
        .drop_duplicates(["symbol", "report_period"], keep="first")
        .reset_index(drop=True)
    )


def build_disclosure_calendar(
    universe_path: Path,
    start_date: str,
    end_date: str,
    output_path: Path,
    refresh: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build or resume a report disclosure calendar."""

    universe = pd.read_csv(universe_path, dtype={"symbol": str})
    rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    completed_symbols: set[str] = set()

    if output_path.exists() and not refresh:
        existing = pd.read_csv(output_path, dtype={"symbol": str, "report_period": str})
        if not existing.empty:
            rows.extend(existing.to_dict("records"))
            completed_symbols = set(existing["symbol"].astype(str))
            print(f"断点续跑：已读取 {len(completed_symbols)} 只股票的披露日历。")

    for _, stock in universe.iterrows():
        symbol = str(stock["symbol"])
        name = str(stock.get("name", ""))
        if symbol in completed_symbols:
            print(f"跳过已完成：{symbol} {name}")
            continue

        print(f"获取披露日历：{symbol} {name}")
        try:
            frame = fetch_symbol_disclosures(symbol, name, start_date, end_date)
            rows.extend(frame.to_dict("records"))
            print(f"  OK：{symbol} {name}，{len(frame)} 条")
        except Exception as exc:  # noqa: BLE001 - 批量抓取需要继续后续股票
            errors.append(
                {
                    "symbol": symbol,
                    "name": name,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            print(f"  FAIL：{symbol} {name} -> {type(exc).__name__}: {exc}")

        if rows:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows, columns=OUTPUT_COLUMNS).to_csv(
                output_path,
                index=False,
                encoding="utf-8-sig",
            )

    return (
        pd.DataFrame(rows, columns=OUTPUT_COLUMNS),
        pd.DataFrame(errors, columns=ERROR_COLUMNS),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--errors", type=Path, default=DEFAULT_ERROR_PATH)
    parser.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    calendar, errors = build_disclosure_calendar(
        universe_path=args.universe,
        start_date=args.start_date,
        end_date=args.end_date,
        output_path=args.output,
        refresh=args.refresh,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    calendar.to_csv(args.output, index=False, encoding="utf-8-sig")
    errors.to_csv(args.errors, index=False, encoding="utf-8-sig")

    print("\n输出完成")
    print(f"披露日历：{args.output}，共 {len(calendar)} 行")
    print(f"错误表：{args.errors}，共 {len(errors)} 行")
    return 0 if errors.empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
