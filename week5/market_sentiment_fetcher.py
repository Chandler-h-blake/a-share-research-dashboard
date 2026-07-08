"""第五周：市场情绪文本抓取模块。

本脚本为 TOP5 股票抓取可用于 LLM 情绪分析的真实文本材料。
数据源采取“接口优先、失败留痕”的原则：

- 东方财富个股新闻：使用 AkShare stock_news_em。
- 东方财富股吧：尝试读取公开页面标题。
- 雪球：尝试读取公开页面标题。

如果某个来源抓取失败，只把失败原因写入 fetch_status，不生成虚假文本。
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd
import requests
from bs4 import BeautifulSoup

from stock_context_builder import load_week4_data


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "week5/sentiment_inputs"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


@dataclass(frozen=True)
class TargetStock:
    symbol: str
    name: str


def normalize_symbol(value: Any) -> str:
    return str(value).strip().zfill(6)


def get_top_targets(top_n: int) -> list[TargetStock]:
    top_pool, _, _ = load_week4_data()
    top = top_pool.sort_values("rank").head(top_n)
    return [
        TargetStock(symbol=normalize_symbol(row["symbol"]), name=str(row["name"]))
        for _, row in top.iterrows()
    ]


def empty_record(stock: TargetStock, source: str, status: str) -> dict[str, str]:
    return {
        "symbol": stock.symbol,
        "name": stock.name,
        "source": source,
        "title": "",
        "content": "",
        "url": "",
        "publish_time": "",
        "fetch_status": status,
    }


def fetch_eastmoney_news(stock: TargetStock, limit: int) -> list[dict[str, str]]:
    try:
        news_df = ak.stock_news_em(symbol=stock.symbol)
    except Exception as exc:  # noqa: BLE001 - 需要把外部接口失败原因写入产物
        return [empty_record(stock, "eastmoney_news", f"failed: {exc}")]

    if news_df.empty:
        return [empty_record(stock, "eastmoney_news", "empty")]

    records: list[dict[str, str]] = []
    for _, row in news_df.head(limit).iterrows():
        title = str(row.get("新闻标题", "")).strip()
        content = str(row.get("新闻内容", "")).strip()
        if not title and not content:
            continue
        records.append(
            {
                "symbol": stock.symbol,
                "name": stock.name,
                "source": "eastmoney_news",
                "title": title,
                "content": content,
                "url": str(row.get("新闻链接", "")).strip(),
                "publish_time": str(row.get("发布时间", "")).strip(),
                "fetch_status": "ok",
            }
        )
    return records or [empty_record(stock, "eastmoney_news", "empty_after_clean")]


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_guba_posts(stock: TargetStock, limit: int) -> list[dict[str, str]]:
    url = f"https://guba.eastmoney.com/list,{stock.symbol}.html"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return [empty_record(stock, "eastmoney_guba", f"failed: {exc}")]

    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[tuple[str, str]] = []
    for link in soup.select("a"):
        title = clean_text(link.get_text(" "))
        href = str(link.get("href", "")).strip()
        if len(title) < 6:
            continue
        if "股吧" in title or stock.name in title or stock.symbol in title or "资讯" in title:
            full_url = href
            if href.startswith("/"):
                full_url = f"https://guba.eastmoney.com{href}"
            candidates.append((title, full_url))

    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for title, link in candidates:
        if title in seen:
            continue
        seen.add(title)
        records.append(
            {
                "symbol": stock.symbol,
                "name": stock.name,
                "source": "eastmoney_guba",
                "title": title,
                "content": "",
                "url": link,
                "publish_time": "",
                "fetch_status": "ok",
            }
        )
        if len(records) >= limit:
            break

    return records or [empty_record(stock, "eastmoney_guba", "empty_or_blocked")]


def xueqiu_symbol(symbol: str) -> str:
    if symbol.startswith(("0", "3")):
        return f"SZ{symbol}"
    if symbol.startswith("6"):
        return f"SH{symbol}"
    return symbol


def fetch_xueqiu_posts(stock: TargetStock, limit: int) -> list[dict[str, str]]:
    xq_symbol = xueqiu_symbol(stock.symbol)
    url = f"https://xueqiu.com/S/{xq_symbol}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return [empty_record(stock, "xueqiu", f"failed: {exc}")]

    soup = BeautifulSoup(response.text, "html.parser")
    texts: list[str] = []
    for selector in ["title", "h1", "h2", "a"]:
        for node in soup.select(selector):
            text = clean_text(node.get_text(" "))
            if stock.name in text or stock.symbol in text or xq_symbol in text:
                texts.append(text)

    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for text in texts:
        if len(text) < 6 or text in seen:
            continue
        seen.add(text)
        records.append(
            {
                "symbol": stock.symbol,
                "name": stock.name,
                "source": "xueqiu",
                "title": text,
                "content": "",
                "url": url,
                "publish_time": "",
                "fetch_status": "ok",
            }
        )
        if len(records) >= limit:
            break

    return records or [empty_record(stock, "xueqiu", "empty_or_login_required")]


def fetch_for_stock(stock: TargetStock, per_source_limit: int) -> pd.DataFrame:
    records: list[dict[str, str]] = []
    records.extend(fetch_eastmoney_news(stock, per_source_limit))
    records.extend(fetch_guba_posts(stock, per_source_limit))
    records.extend(fetch_xueqiu_posts(stock, per_source_limit))
    return pd.DataFrame.from_records(records)


def write_sentiment_inputs(top_n: int, output_dir: Path, per_source_limit: int) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for stock in get_top_targets(top_n):
        df = fetch_for_stock(stock, per_source_limit)
        output_path = output_dir / f"{stock.symbol}_sentiment_texts.csv"
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        written.append(output_path)
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--per-source-limit", type=int, default=8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    written = write_sentiment_inputs(args.top_n, args.output_dir, args.per_source_limit)
    print("第五周市场情绪文本抓取完成")
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
