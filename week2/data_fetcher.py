from pathlib import Path
import sys
import akshare as ak
import pandas as pd



def normalize_stock_symbol(symbol: str) -> str:
    """
    把股票代码整理成 AkShare 的格式。
    """
    symbol = str(symbol).strip().lower()

    if symbol.startswith(("sh", "sz", "bj")):
        return symbol

    if symbol.startswith("6"):
        return f"sh{symbol}"

    if symbol.startswith(("0", "3")):
        return f"sz{symbol}"

    if symbol.startswith(("4", "8")):
        return f"bj{symbol}"

    raise ValueError(f"无法判断股票代码属于哪个市场：{symbol}")


def normalize_plain_stock_code(symbol: str) -> str:
    """把 sh600519 / sz300750 这种代码转成 600519 / 300750。"""
    symbol = str(symbol).strip().lower()
    if symbol.startswith(("sh", "sz", "bj")):
        return symbol[2:]
    return symbol


def get_stock_market(symbol: str) -> str:
    """资金流接口需要 market 参数，这里从股票代码里判断是 sh 还是 sz。"""
    normalized = normalize_stock_symbol(symbol)
    if normalized.startswith("sh"):
        return "sh"
    if normalized.startswith("sz"):
        return "sz"
    if normalized.startswith("bj"):
        return "bj"
    raise ValueError(f"无法判断股票市场：{symbol}")


def normalize_index_symbol(index_code: str) -> str:
    """
    把指数代码整理成备用接口常用的格式。

    例子：
    - 000300 -> sh000300，沪深300
    - 000001 -> sh000001，上证指数
    - 399001 -> sz399001，深证成指
    """
    index_code = str(index_code).strip().lower()

    if index_code.startswith(("sh", "sz")):
        return index_code

    if index_code.startswith("399"):
        return f"sz{index_code}"

    return f"sh{index_code}"


def normalize_plain_index_code(index_code: str) -> str:
    """把 sh000300 / sz399001 这种指数代码转成 000300 / 399001。"""
    index_code = str(index_code).strip().lower()
    if index_code.startswith(("sh", "sz")):
        return index_code[2:]
    return index_code


def get_daily_data(
    symbol: str,
    start_date: str,
    end_date: str,
    adjust: str = "qfq",
) -> pd.DataFrame:
    """
    获取个股日线数据。

    adjust 参数：
    - "qfq"：前复权
    - "hfq"：后复权
    - ""：不复权
    """
    ak_symbol = normalize_stock_symbol(symbol)

    df = ak.stock_zh_a_daily(
        symbol=ak_symbol,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )

    df = clean_daily_data(df)
    df["stock_code"] = ak_symbol
    return df


def get_index_data(index_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取指数日线数据。

    - 000300：沪深300
    - 000905：中证500
    - 000001：上证指数
    """
    index_code = str(index_code).strip()

    errors = []

    try:
        df = ak.index_zh_a_hist(
            symbol=index_code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as primary_error:
        errors.append(f"index_zh_a_hist: {primary_error}")
        fallback_symbol = normalize_index_symbol(index_code)
        try:
            df = ak.stock_zh_index_daily(symbol=fallback_symbol)
        except Exception as fallback_error:
            errors.append(f"stock_zh_index_daily: {fallback_error}")
            csi_symbol = normalize_plain_index_code(index_code)
            try:
                df = ak.stock_zh_index_hist_csindex(
                    symbol=csi_symbol,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as csi_error:
                errors.append(f"stock_zh_index_hist_csindex: {csi_error}")
                error_text = "\n".join(errors)
                raise RuntimeError(
                    "指数数据获取失败。已经依次尝试 index_zh_a_hist、"
                    "stock_zh_index_daily、stock_zh_index_hist_csindex，"
                    f"但都没有成功。\n具体错误：\n{error_text}"
                ) from csi_error

    rename_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "涨跌幅": "pct_change",
    }
    df = df.rename(columns=rename_map)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        df = df[(df["date"] >= start) & (df["date"] <= end)]

    df["index_code"] = index_code
    return df.sort_values("date").reset_index(drop=True)


def get_north_flow(start_date: str, end_date: str) -> pd.DataFrame:
    """
    获取北向资金流向。

    这个接口不同 AkShare 版本可能会变化。如果运行失败，先不要怀疑自己，
    先检查 akshare 版本和网络。
    """
    df = ak.stock_hsgt_hist_em(symbol="北向资金")

    rename_map = {
        "日期": "date",
        "当日成交净买额": "net_buy_amount",
        "买入成交额": "buy_amount",
        "卖出成交额": "sell_amount",
        "历史累计净买额": "total_net_buy_amount",
    }
    df = df.rename(columns=rename_map)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        df = df[(df["date"] >= start) & (df["date"] <= end)]

    return df.sort_values("date").reset_index(drop=True)


def get_financial_data(symbol: str) -> pd.DataFrame:
    """获取个股财务摘要数据。"""
    plain_code = normalize_plain_stock_code(symbol)
    return ak.stock_financial_abstract(symbol=plain_code)


def clean_daily_data(df: pd.DataFrame) -> pd.DataFrame:
    """清洗日线数据：整理日期、排序、去掉关键字段缺失的行。"""
    df = df.copy()

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])

    key_columns = ["date", "open", "high", "low", "close", "volume"]
    existing_key_columns = [col for col in key_columns if col in df.columns]

    df = df.dropna(subset=existing_key_columns)

    if "date" in df.columns:
        df = df.sort_values("date")

    return df.reset_index(drop=True)


def add_basic_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    添加基础技术指标。

    先算这些就够第二周使用：
    - ma5：5日均线
    - ma20：20日均线
    - daily_return：日收益率
    - volume_ma5：5日成交量均线
    """
    df = df.copy()

    if "date" in df.columns:
        sort_columns = ["date"]
        if "stock_code" in df.columns:
            sort_columns = ["stock_code", "date"]
        df = df.sort_values(sort_columns)

    group_key = "stock_code" if "stock_code" in df.columns else None

    if group_key:
        grouped_close = df.groupby(group_key)["close"]
        grouped_volume = df.groupby(group_key)["volume"]
        df["ma5"] = grouped_close.transform(lambda series: series.rolling(5).mean())
        df["ma20"] = grouped_close.transform(lambda series: series.rolling(20).mean())
        df["daily_return"] = grouped_close.pct_change()
        df["volume_ma5"] = grouped_volume.transform(lambda series: series.rolling(5).mean())
    else:
        df["ma5"] = df["close"].rolling(5).mean()
        df["ma20"] = df["close"].rolling(20).mean()
        df["daily_return"] = df["close"].pct_change()
        df["volume_ma5"] = df["volume"].rolling(5).mean()

    return df.reset_index(drop=True)


def save_data(df: pd.DataFrame, output_path: str | Path) -> None:
    """保存数据到 csv。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")


def main() -> None:
    print("A股数据获取工具")
    print("日期格式示例：20250101")
    print("请选择要获取的数据：")
    print("1. 个股日线数据")
    print("2. 指数日线数据")
    print("3. 北向资金流向")
    print("4. 个股财务摘要")

    choice = input("请输入 1/2/3/4：").strip()

    if choice == "1":
        print("复权方式：qfq=前复权，hfq=后复权，直接回车=前复权")
        symbol = input("请输入股票代码，比如 600519 / 300750 / 002594：").strip()
        start_date = input("请输入开始日期：").strip()
        end_date = input("请输入结束日期：").strip()
        adjust = input("请输入复权方式 qfq/hfq，直接回车默认 qfq：").strip() or "qfq"

        if adjust not in {"qfq", "hfq", ""}:
            raise ValueError("复权方式只能输入 qfq、hfq，或者直接回车")

        result_df = get_daily_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
        result_df = add_basic_indicators(result_df)

        stock_code = normalize_stock_symbol(symbol)
        output_path = f"week2/data/{stock_code}_{start_date}_{end_date}_{adjust or 'no_adjust'}_daily.csv"

    elif choice == "2":
        index_code = input("请输入指数代码，比如 000300 / 000905 / 000001：").strip()
        start_date = input("请输入开始日期：").strip()
        end_date = input("请输入结束日期：").strip()

        result_df = get_index_data(
            index_code=index_code,
            start_date=start_date,
            end_date=end_date,
        )
        output_path = f"week2/data/index_{index_code}_{start_date}_{end_date}.csv"

    elif choice == "3":
        start_date = input("请输入开始日期：").strip()
        end_date = input("请输入结束日期：").strip()

        result_df = get_north_flow(
            start_date=start_date,
            end_date=end_date,
        )
        output_path = f"week2/data/north_flow_{start_date}_{end_date}.csv"

    elif choice == "4":
        symbol = input("请输入股票代码，比如 600519 / 300750 / 002594：").strip()

        result_df = get_financial_data(symbol=symbol)
        stock_code = normalize_plain_stock_code(symbol)
        output_path = f"week2/data/{stock_code}_financial_abstract.csv"

    else:
        raise ValueError("只能输入 1、2、3、4")

    save_data(result_df, output_path)

    print(result_df.head())
    print(f"保存完成：{output_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"运行失败：{exc}")
        print("如果看到 ConnectionError 或 RemoteDisconnected，通常是数据源接口临时不稳定。")
        sys.exit(1)
