"""完整 A 股中长期投研看板。

整合内容：
- Week3 市场概览
- Week4 因子选股
- Week5 LLM 多 Agent 投研
- 资金监控
- 数据刷新与参数设置
"""

from __future__ import annotations

import os
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable
import urllib.error
import urllib.request

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import akshare as ak
except ImportError:
    ak = None


ROOT = Path(__file__).resolve().parent
WEEK4_DATA = ROOT / "week4/data"
WEEK5_DIR = ROOT / "week5"
WEEK5_OUTPUTS = WEEK5_DIR / "outputs"
WEEK6_DIR = ROOT / "week6"
WEEK6_DATA = WEEK6_DIR / "data"

FACTOR_COLUMNS = {
    "成长": ["revenue_growth_yoy_weighted_score", "net_profit_growth_yoy_weighted_score"],
    "动量": ["momentum_20d_weighted_score", "turnover_change_weighted_score"],
    "质量": ["roe_weighted_score", "gross_margin_weighted_score"],
    "价值": ["pe_percentile_weighted_score", "pb_percentile_weighted_score"],
    "波动": ["volatility_60d_weighted_score"],
}


st.set_page_config(page_title="A股中长期投研看板 Final", layout="wide")

st.markdown(
    """
    <style>
    .block-container { padding-top: 2.4rem; max-width: 96%; }
    h1 { font-size: 2.05rem !important; line-height: 1.25 !important; margin-top: 0.2rem !important; }
    h2 { font-size: 1.35rem !important; margin-top: 0.8rem !important; }
    h3 { font-size: 1.05rem !important; margin-top: 0.5rem !important; }
    [data-testid="stMetric"] { padding: 0.35rem 0.5rem; }
    [data-testid="stMetricValue"] { font-size: 1.2rem; }
    [data-testid="stSidebar"] .block-container {
        padding-top: 2.1rem;
        padding-left: 1.65rem;
        padding-right: 1.45rem;
    }
    .sidebar-title {
        font-size: 1.72rem;
        line-height: 1.22;
        font-weight: 800;
        color: #262730;
        margin-bottom: 0.55rem;
    }
    .sidebar-subtitle {
        font-size: 1.02rem;
        line-height: 1.45;
        color: #747987;
        font-weight: 650;
        margin-bottom: 1.35rem;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label {
        margin-bottom: 0.55rem;
    }
    [data-testid="stSidebar"] [role="radiogroup"] p {
        font-size: 1.06rem;
        font-weight: 650;
    }
    [data-testid="stSidebar"] hr {
        margin-top: 1.7rem;
        margin-bottom: 1.5rem;
    }
    .sidebar-note {
        font-size: 0.98rem;
        line-height: 1.65;
        color: #7b8190;
        font-weight: 560;
    }
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"],
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {
        word-break: break-word;
        overflow-wrap: anywhere;
        white-space: normal;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def require_akshare() -> None:
    if ak is None:
        raise RuntimeError("当前环境没有安装 akshare")


def read_csv(path: Path, dtype: dict[str, object] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"找不到文件：{path}")
    return pd.read_csv(path, dtype=dtype, encoding="utf-8-sig")


def format_file_time(path: Path) -> str:
    if not path.exists():
        return "文件不存在"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def numeric_frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = df.copy()
    for col in columns:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")
    return result


@st.cache_data(ttl=300)
def load_index_overview_data() -> pd.DataFrame:
    require_akshare()
    target_names = ["上证指数", "深证成指", "创业板指", "科创50"]
    errors: list[str] = []

    try:
        raw_df = ak.stock_zh_index_spot_em(symbol="沪深重要指数")
        data_source = "AkShare stock_zh_index_spot_em / 东方财富"
    except Exception as em_error:  # noqa: BLE001
        errors.append(f"东方财富指数接口失败：{em_error}")
        try:
            raw_df = ak.stock_zh_index_spot_sina()
            data_source = "AkShare stock_zh_index_spot_sina / 新浪财经"
        except Exception as sina_error:  # noqa: BLE001
            errors.append(f"新浪指数接口失败：{sina_error}")
            raise RuntimeError("；".join(errors)) from sina_error

    required_columns = ["代码", "名称", "最新价", "涨跌幅", "成交额"]
    missing = [col for col in required_columns if col not in raw_df.columns]
    if missing:
        raise RuntimeError(f"指数接口返回结果缺少字段：{missing}")

    result = raw_df[required_columns].copy()
    result = result[result["名称"].isin(target_names)].copy()
    if result.empty:
        raise RuntimeError("指数接口返回结果中没有找到目标指数")

    result = numeric_frame(result, ["最新价", "涨跌幅", "成交额"])
    result["成交额"] = result["成交额"] / 100000000
    result["数据源"] = data_source
    result = result.rename(columns={"名称": "指数", "最新价": "点位"})
    order_map = {name: index for index, name in enumerate(target_names)}
    result["排序"] = result["指数"].map(order_map)
    return result.sort_values("排序").drop(columns=["排序"]).reset_index(drop=True)


@st.cache_data(ttl=300)
def load_industry_heatmap_data() -> pd.DataFrame:
    require_akshare()
    errors: list[str] = []

    try:
        raw_df = ak.index_realtime_sw(symbol="一级行业")
        required_columns = ["指数名称", "昨收盘", "最新价"]
        missing = [col for col in required_columns if col not in raw_df.columns]
        if missing:
            raise RuntimeError(f"申万接口返回结果缺少字段：{missing}")
        result = raw_df[required_columns].copy()
        result = numeric_frame(result, ["昨收盘", "最新价"])
        result["涨跌幅"] = (result["最新价"] - result["昨收盘"]) / result["昨收盘"] * 100
        result = result.rename(columns={"指数名称": "行业"})
        result = result[["行业", "涨跌幅"]].dropna(subset=["涨跌幅"])
        result["数据源"] = "AkShare index_realtime_sw / 申万一级行业"
        return result.head(31).reset_index(drop=True)
    except Exception as sw_error:  # noqa: BLE001
        errors.append(f"申万行业接口失败：{sw_error}")

    try:
        raw_df = ak.stock_board_industry_name_em()
        required_columns = ["板块名称", "涨跌幅"]
        missing = [col for col in required_columns if col not in raw_df.columns]
        if missing:
            raise RuntimeError(f"东方财富行业接口返回结果缺少字段：{missing}")
        result = raw_df[required_columns].copy()
        result["涨跌幅"] = pd.to_numeric(result["涨跌幅"], errors="coerce")
        result = result.rename(columns={"板块名称": "行业"})
        result = result[["行业", "涨跌幅"]].dropna(subset=["涨跌幅"])
        result["数据源"] = "AkShare stock_board_industry_name_em / 东方财富行业板块"
        return result.head(31).reset_index(drop=True)
    except Exception as em_error:  # noqa: BLE001
        errors.append(f"东方财富行业接口失败：{em_error}")
        raise RuntimeError("；".join(errors)) from em_error


@st.cache_data(ttl=300)
def load_market_spot_data() -> pd.DataFrame:
    require_akshare()
    errors: list[str] = []

    try:
        raw_df = ak.stock_zh_a_spot_em()
        required_columns = ["代码", "名称", "涨跌幅", "成交额", "换手率"]
        missing = [col for col in required_columns if col not in raw_df.columns]
        if missing:
            raise RuntimeError(f"东方财富接口返回结果缺少字段：{missing}")
        result = raw_df[required_columns].copy()
        data_source = "AkShare stock_zh_a_spot_em / 东方财富"
    except Exception as em_error:  # noqa: BLE001
        errors.append(f"东方财富接口失败：{em_error}")
        try:
            raw_df = ak.stock_zh_a_spot()
            required_columns = ["代码", "名称", "涨跌幅", "成交额"]
            missing = [col for col in required_columns if col not in raw_df.columns]
            if missing:
                raise RuntimeError(f"新浪接口返回结果缺少字段：{missing}")
            result = raw_df[required_columns].copy()
            result["换手率"] = pd.NA
            data_source = "AkShare stock_zh_a_spot / 新浪财经"
        except Exception as sina_error:  # noqa: BLE001
            errors.append(f"新浪接口失败：{sina_error}")
            raise RuntimeError("；".join(errors)) from sina_error

    result = numeric_frame(result, ["涨跌幅", "成交额", "换手率"])
    result = result.dropna(subset=["成交额"])
    result["成交额"] = result["成交额"] / 100000000
    result["数据源"] = data_source
    return result.reset_index(drop=True)


def build_market_distribution_data(market_df: pd.DataFrame) -> pd.DataFrame:
    pct_change = pd.to_numeric(market_df["涨跌幅"], errors="coerce").dropna()
    return pd.DataFrame(
        {
            "类型": ["上涨", "下跌", "平盘", "涨停", "跌停", "涨幅>5%", "跌幅<-5%"],
            "数量": [
                int((pct_change > 0).sum()),
                int((pct_change < 0).sum()),
                int((pct_change == 0).sum()),
                int((pct_change >= 9.8).sum()),
                int((pct_change <= -9.8).sum()),
                int((pct_change > 5).sum()),
                int((pct_change < -5).sum()),
            ],
        }
    )


def render_market_overview() -> None:
    st.title("📊 市场概览")
    st.caption("对应 Week3 市场概览面板：指数行情、行业热力图、涨跌分布、成交额 TOP20。")

    try:
        index_data = load_index_overview_data()
        source = index_data["数据源"].iloc[0]
        st.caption(f"指数数据来源：{source}。成交额单位：亿元。")
        index_view = index_data.drop(columns=["数据源"])
        cols = st.columns(4)
        for i, row in index_view.iterrows():
            cols[i].metric(row["指数"], f'{row["点位"]:.2f}', f'{row["涨跌幅"]:.2f}%')
    except Exception as exc:  # noqa: BLE001
        st.warning(f"指数真实数据获取失败：{exc}")
        index_view = pd.DataFrame()

    col_left, col_right = st.columns([1, 1])
    with col_left:
        st.subheader("指数涨跌幅")
        if not index_view.empty:
            fig = px.bar(
                index_view,
                x="指数",
                y="涨跌幅",
                color="涨跌幅",
                color_continuous_scale=["green", "white", "red"],
                text="涨跌幅",
            )
            fig.update_layout(height=280, margin=dict(l=10, r=10, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(index_view, use_container_width=True, hide_index=True)

    with col_right:
        st.subheader("行业热力图")
        try:
            industry_data = load_industry_heatmap_data()
            st.caption(f"行业数据来源：{industry_data['数据源'].iloc[0]}。")
            render_industry_heatmap(industry_data.drop(columns=["数据源"]))
        except Exception as exc:  # noqa: BLE001
            st.warning(f"行业真实数据获取失败：{exc}")

    try:
        market_df = load_market_spot_data()
        st.caption(f"全市场数据来源：{market_df['数据源'].iloc[0]}。成交额单位：亿元。")
        distribution = build_market_distribution_data(market_df)
        top_amount = market_df.sort_values("成交额", ascending=False).head(20)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"全市场实时行情获取失败：{exc}")
        distribution = pd.DataFrame()
        top_amount = pd.DataFrame()

    col_dist, col_top = st.columns([1, 1.4])
    with col_dist:
        st.subheader("涨跌分布")
        if not distribution.empty:
            dist_map = dict(zip(distribution["类型"], distribution["数量"]))
            c1, c2, c3 = st.columns(3)
            c1.metric("上涨", dist_map.get("上涨", 0))
            c2.metric("下跌", dist_map.get("下跌", 0))
            c3.metric("平盘", dist_map.get("平盘", 0))
            fig = px.bar(
                distribution,
                x="类型",
                y="数量",
                color="类型",
                text="数量",
                color_discrete_map={
                    "上涨": "red",
                    "下跌": "green",
                    "平盘": "gray",
                    "涨停": "darkred",
                    "跌停": "darkgreen",
                    "涨幅>5%": "orangered",
                    "跌幅<-5%": "seagreen",
                },
            )
            fig.update_layout(height=280, margin=dict(l=10, r=10, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)
    with col_top:
        st.subheader("成交额 TOP20")
        if not top_amount.empty:
            display_cols = [col for col in ["代码", "名称", "涨跌幅", "成交额", "换手率"] if col in top_amount.columns]
            st.dataframe(top_amount[display_cols], use_container_width=True, hide_index=True)
            fig = px.bar(
                top_amount,
                x="名称",
                y="成交额",
                color="涨跌幅",
                color_continuous_scale=["green", "white", "red"],
                text="成交额",
            )
            fig.update_layout(height=340, margin=dict(l=10, r=10, t=20, b=70))
            fig.update_xaxes(categoryorder="array", categoryarray=top_amount["名称"].tolist())
            st.plotly_chart(fig, use_container_width=True)


def render_industry_heatmap(industry_data: pd.DataFrame) -> None:
    rows, cols = 4, 8
    padded = industry_data[["行业", "涨跌幅"]].copy()
    while len(padded) < rows * cols:
        padded.loc[len(padded)] = {"行业": "", "涨跌幅": None}

    z_values: list[list[float | None]] = []
    text_values: list[list[str]] = []
    for row_index in range(rows):
        row_slice = padded.iloc[row_index * cols : (row_index + 1) * cols]
        z_values.append(row_slice["涨跌幅"].tolist())
        text_values.append(
            [
                f'{item["行业"]}<br>{item["涨跌幅"]:.2f}%'
                if pd.notna(item["涨跌幅"])
                else ""
                for _, item in row_slice.iterrows()
            ]
        )

    fig = go.Figure(
        data=go.Heatmap(
            z=z_values,
            text=text_values,
            texttemplate="%{text}",
            textfont={"size": 13},
            colorscale=[[0.0, "green"], [0.5, "white"], [1.0, "red"]],
            zmin=-3,
            zmax=3,
            hovertemplate="%{text}<extra></extra>",
            colorbar=dict(title="涨跌幅"),
        )
    )
    fig.update_layout(
        height=340,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, autorange="reversed"),
        margin=dict(l=10, r=10, t=20, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


@st.cache_data(ttl=120)
def load_factor_outputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    top_pool = read_csv(WEEK4_DATA / "final_top30_stock_pool.csv", dtype={"symbol": str})
    scores = read_csv(WEEK4_DATA / "final_factor_scores.csv", dtype={"symbol": str})
    overview = read_csv(WEEK4_DATA / "final_factor_overview.csv")
    return top_pool, scores, overview


def category_scores(row: pd.Series) -> pd.DataFrame:
    records = []
    for category, columns in FACTOR_COLUMNS.items():
        available = [col for col in columns if col in row.index]
        value = sum(float(row[col]) for col in available if pd.notna(row[col]))
        records.append({"维度": category, "贡献": value})
    return pd.DataFrame(records)


def render_factor_selection() -> None:
    st.title("🔍 因子选股")
    st.caption("对应 Week4：因子排名、精选股票池、个股因子得分雷达图。")
    try:
        top_pool, scores, overview = load_factor_outputs()
    except Exception as exc:  # noqa: BLE001
        st.error(f"读取 Week4 因子产物失败：{exc}")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("精选股票池", f"{len(top_pool)} 只")
    c2.metric("全量得分股票", f"{len(scores)} 只")
    c3.metric("因子数量", f"{len(overview)} 个")
    st.caption(f"TOP30更新时间：{format_file_time(WEEK4_DATA / 'final_top30_stock_pool.csv')}")

    st.subheader("精选股票池 TOP30")
    show_cols = [
        col
        for col in ["rank", "symbol", "name", "industry", "composite_score"]
        if col in top_pool.columns
    ]
    st.dataframe(top_pool[show_cols], use_container_width=True, hide_index=True)

    col_rank, col_radar = st.columns([1.1, 1])
    with col_rank:
        st.subheader("因子排名")
        rank_df = top_pool.head(15).copy()
        fig = px.bar(
            rank_df.sort_values("composite_score"),
            x="composite_score",
            y="name",
            orientation="h",
            color="composite_score",
            color_continuous_scale="RdYlGn_r",
            text="composite_score",
        )
        fig.update_layout(height=460, margin=dict(l=10, r=10, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_radar:
        st.subheader("个股因子得分雷达图")
        options = [
            f"{str(row['symbol']).zfill(6)} {row['name']}"
            for _, row in top_pool.iterrows()
        ]
        selected = st.selectbox("选择股票", options)
        symbol = selected.split()[0]
        rows = scores[scores["symbol"].astype(str).str.zfill(6) == symbol]
        if rows.empty:
            st.warning("得分表中找不到该股票。")
        else:
            radar_df = category_scores(rows.iloc[0])
            fig = go.Figure()
            fig.add_trace(
                go.Scatterpolar(
                    r=radar_df["贡献"].tolist() + [radar_df["贡献"].iloc[0]],
                    theta=radar_df["维度"].tolist() + [radar_df["维度"].iloc[0]],
                    fill="toself",
                    name=selected,
                )
            )
            fig.update_layout(height=430, polar=dict(radialaxis=dict(visible=True)))
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(radar_df, use_container_width=True, hide_index=True)

    with st.expander("因子说明与权重"):
        display_cols = [
            col
            for col in [
                "factor",
                "name",
                "category",
                "direction_text",
                "weight",
                "description",
                "spearman_ic_adjusted",
                "group1_minus_group5",
            ]
            if col in overview.columns
        ]
        st.dataframe(overview[display_cols], use_container_width=True, hide_index=True)


def stock_label(row: pd.Series) -> str:
    return f"{str(row['symbol']).zfill(6)} {row['name']}"


def format_compare_table(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    percent_cols = [
        "momentum_20d",
        "pe_percentile",
        "pb_percentile",
        "roe",
        "gross_margin",
        "revenue_growth_yoy",
        "net_profit_growth_yoy",
        "volatility_60d",
    ]
    for col in percent_cols:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")
    return result


def render_stock_compare() -> None:
    st.title("🧭 个股对比")
    st.caption("对应 6.2 特色功能：从 Week4 TOP30 中选择 2-5 只股票，横向比较因子、财务和风险指标。")

    try:
        top_pool, scores, _ = load_factor_outputs()
    except Exception as exc:  # noqa: BLE001
        st.error(f"读取 Week4 因子产物失败：{exc}")
        return

    options = [stock_label(row) for _, row in top_pool.iterrows()]
    default_options = options[: min(3, len(options))]
    selected = st.multiselect("选择 2-5 只股票", options, default=default_options, max_selections=5)
    if len(selected) < 2:
        st.info("请至少选择 2 只股票进行对比。")
        return

    symbols = [item.split()[0] for item in selected]
    compare = top_pool[top_pool["symbol"].astype(str).str.zfill(6).isin(symbols)].copy()
    score_rows = scores[scores["symbol"].astype(str).str.zfill(6).isin(symbols)].copy()

    c1, c2, c3 = st.columns(3)
    best = compare.sort_values("composite_score", ascending=False).iloc[0]
    c1.metric("对比股票数", f"{len(compare)} 只")
    c2.metric("最高综合得分", f"{best['composite_score']:.3f}", f"{str(best['symbol']).zfill(6)} {best['name']}")
    c3.metric("平均排名", f"{compare['rank'].mean():.1f}")

    show_cols = [
        "rank",
        "symbol",
        "name",
        "industry",
        "composite_score",
        "momentum_20d",
        "roe",
        "gross_margin",
        "revenue_growth_yoy",
        "net_profit_growth_yoy",
        "pe_percentile",
        "pb_percentile",
        "volatility_60d",
    ]
    st.subheader("核心指标对比")
    st.dataframe(
        format_compare_table(compare[[col for col in show_cols if col in compare.columns]]),
        use_container_width=True,
        hide_index=True,
    )

    col_bar, col_radar = st.columns([1, 1])
    with col_bar:
        st.subheader("综合得分")
        fig = px.bar(
            compare.sort_values("composite_score"),
            x="composite_score",
            y="name",
            orientation="h",
            color="composite_score",
            color_continuous_scale="RdYlGn_r",
            text="composite_score",
        )
        fig.update_layout(height=390, margin=dict(l=10, r=10, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_radar:
        st.subheader("五维因子贡献雷达")
        fig = go.Figure()
        for _, row in score_rows.iterrows():
            radar_df = category_scores(row)
            fig.add_trace(
                go.Scatterpolar(
                    r=radar_df["贡献"].tolist() + [radar_df["贡献"].iloc[0]],
                    theta=radar_df["维度"].tolist() + [radar_df["维度"].iloc[0]],
                    fill="toself",
                    name=f"{str(row['symbol']).zfill(6)} {row['name']}",
                    opacity=0.68,
                )
            )
        fig.update_layout(height=390, polar=dict(radialaxis=dict(visible=True)), showlegend=True)
        st.plotly_chart(fig, use_container_width=True)


def compact_records(df: pd.DataFrame, columns: list[str], limit: int = 20) -> list[dict[str, object]]:
    available = [col for col in columns if col in df.columns]
    if not available or df.empty:
        return []
    return df[available].head(limit).to_dict(orient="records")


def frame_to_markdown(df: pd.DataFrame) -> str:
    try:
        return df.to_markdown(index=False)
    except Exception:  # noqa: BLE001
        return df.to_string(index=False)


def build_daily_review_context(review_date: str) -> str:
    sections: list[str] = [f"# A股每日复盘结构化材料\n\n复盘日期：{review_date}"]

    try:
        index_data = load_index_overview_data()
        sections.append("## 指数行情\n" + frame_to_markdown(pd.DataFrame(index_data.drop(columns=["数据源"], errors="ignore"))))
    except Exception as exc:  # noqa: BLE001
        sections.append(f"## 指数行情\n数据获取失败：{exc}")

    try:
        industry_data = load_industry_heatmap_data()
        industry_view = industry_data.drop(columns=["数据源"], errors="ignore").sort_values("涨跌幅", ascending=False)
        sections.append("## 行业涨跌\n" + frame_to_markdown(industry_view))
    except Exception as exc:  # noqa: BLE001
        sections.append(f"## 行业涨跌\n数据获取失败：{exc}")

    try:
        market_df = load_market_spot_data()
        distribution = build_market_distribution_data(market_df)
        top_amount = market_df.sort_values("成交额", ascending=False).head(20)
        sections.append("## 涨跌分布\n" + frame_to_markdown(distribution))
        sections.append(
            "## 成交额 TOP20\n"
            + frame_to_markdown(top_amount[[col for col in ["代码", "名称", "涨跌幅", "成交额", "换手率"] if col in top_amount.columns]])
        )
    except Exception as exc:  # noqa: BLE001
        sections.append(f"## 全市场行情\n数据获取失败：{exc}")

    try:
        main_fund, fn_name = load_main_fund_data()
        fund_cols = preferred_columns(main_fund)
        sections.append(f"## 主力资金\n接口：{fn_name}\n" + frame_to_markdown(main_fund[fund_cols].head(20)))
    except Exception as exc:  # noqa: BLE001
        sections.append(f"## 主力资金\n数据获取失败：{exc}")

    return "\n\n".join(sections)


def generate_daily_review(context: str) -> str:
    api_key_env = os.getenv("LLM_API_KEY_ENV", "DEEPSEEK_API_KEY")
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise RuntimeError(f"未设置 {api_key_env}，无法调用 AI 每日复盘。")

    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/chat/completions")
    model = os.getenv("LLM_MODEL", "deepseek-reasoner")
    prompt = f"""
你是严谨的中文 A 股市场复盘助手。请只基于下面的结构化材料写复盘，不得编造新闻、政策、公告或资金数据。

输出结构：
1. 今日市场概览
2. 行业强弱与轮动线索
3. 成交额与市场情绪
4. 资金面观察
5. 明日跟踪重点
6. 数据限制说明

结构化材料：
{context}
"""
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "你是严谨的中文 A 股投研辅助系统，必须基于输入数据回答。"},
            {"role": "user", "content": prompt},
        ],
    }
    request = urllib.request.Request(
        base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM 请求失败：{exc}") from exc

    try:
        return str(result["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"LLM 返回格式异常：{result}") from exc


def render_daily_review() -> None:
    st.title("📝 AI每日复盘")
    st.caption("对应 6.2 特色功能：收集看板结构化行情材料，并调用 DeepSeek Reasoner 生成日度复盘。")

    default_date = datetime.now().strftime("%Y-%m-%d")
    review_date = st.text_input("复盘日期", value=default_date)
    context = build_daily_review_context(review_date.strip() or default_date)

    with st.expander("复盘输入材料", expanded=False):
        st.markdown(context)

    if st.button("生成 AI 复盘", type="primary", use_container_width=True):
        try:
            with st.spinner("正在调用 LLM 生成复盘..."):
                review = generate_daily_review(context)
            st.markdown(review)
        except Exception as exc:  # noqa: BLE001
            st.error(f"AI 每日复盘生成失败：{exc}")


@st.cache_data(ttl=300)
def load_industry_rotation_data() -> pd.DataFrame:
    return read_csv(WEEK6_DATA / "industry_rotation.csv")


def top_pool_with_mapped_industry(top_pool: pd.DataFrame) -> pd.DataFrame:
    """优先使用 Week5 申万行业映射修正 TOP 股票池行业。"""

    result = top_pool.copy()
    result["symbol"] = result["symbol"].astype(str).str.zfill(6)
    mapping_path = WEEK5_DIR / "industry_mapping.csv"
    if not mapping_path.exists():
        result["industry_display"] = result["industry"].fillna("未映射")
        return result

    mapping = read_csv(mapping_path, dtype={"symbol": str, "industry_code": str})
    mapping["symbol"] = mapping["symbol"].astype(str).str.zfill(6)
    mapping = mapping[["symbol", "industry"]].rename(columns={"industry": "mapped_industry"})
    result = result.merge(mapping, on="symbol", how="left")
    original_industry = result["industry"].fillna("").astype(str)
    mapped_industry = result["mapped_industry"].fillna("").astype(str)
    result["industry_display"] = mapped_industry.where(
        mapped_industry.ne("") & mapped_industry.ne("未识别"),
        original_industry.where(original_industry.ne("") & original_industry.ne("unknown"), "未映射"),
    )
    return result


def render_industry_rotation() -> None:
    st.title("🔁 行业轮动")
    st.caption("对应 6.2 特色功能：基于申万一级行业历史行情，观察近 1 月与近 3 月强弱变化。")

    try:
        rotation = load_industry_rotation_data()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"行业轮动数据不存在或读取失败：{exc}")
        st.info("请到设置页点击“刷新行业轮动”，或运行 python week6/industry_rotation.py。")
        return

    generated = rotation["generated_at"].iloc[0] if "generated_at" in rotation.columns and not rotation.empty else "未知"
    source = rotation["data_source"].iloc[0] if "data_source" in rotation.columns and not rotation.empty else "未知"
    c1, c2, c3 = st.columns(3)
    c1.metric("行业数量", f"{len(rotation)} 个")
    c2.metric("更新时间", str(generated))
    c3.metric("最近交易日", str(rotation["last_date"].max()) if "last_date" in rotation.columns else "未知")
    st.caption(f"数据源：{source}")

    view = rotation.copy()
    for col in ["return_1m", "return_3m"]:
        view[col] = pd.to_numeric(view[col], errors="coerce")
        view[f"{col}_pct"] = view[col] * 100

    col_1m, col_3m = st.columns(2)
    with col_1m:
        st.subheader("近 1 月涨幅榜")
        st.dataframe(
            view.sort_values("rank_1m").head(10)[["rank_1m", "industry_name", "return_1m_pct", "rotation_type"]],
            use_container_width=True,
            hide_index=True,
        )
    with col_3m:
        st.subheader("近 3 月涨幅榜")
        st.dataframe(
            view.sort_values("rank_3m").head(10)[["rank_3m", "industry_name", "return_3m_pct", "rotation_type"]],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("轮动散点图")
    fig = px.scatter(
        view,
        x="return_3m_pct",
        y="return_1m_pct",
        color="rotation_type",
        size="latest_close",
        hover_name="industry_name",
        text="industry_name",
        labels={"return_3m_pct": "近3月涨跌幅(%)", "return_1m_pct": "近1月涨跌幅(%)"},
    )
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    fig.add_vline(x=0, line_dash="dot", line_color="gray")
    fig.update_traces(textposition="top center")
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    col_table, col_pool = st.columns([1.2, 1])
    with col_table:
        st.subheader("轮动分类表")
        st.dataframe(
            view[
                [
                    "industry_code",
                    "industry_name",
                    "return_1m_pct",
                    "rank_1m",
                    "return_3m_pct",
                    "rank_3m",
                    "rotation_type",
                ]
            ].sort_values(["rotation_type", "rank_1m"]),
            use_container_width=True,
            hide_index=True,
        )

    with col_pool:
        st.subheader("TOP30 股票行业分布")
        try:
            top_pool, _, _ = load_factor_outputs()
            top_pool = top_pool_with_mapped_industry(top_pool)
            industry_count = top_pool["industry_display"].value_counts().reset_index()
            industry_count.columns = ["行业", "股票数量"]
            fig_pool = px.bar(industry_count, x="行业", y="股票数量", text="股票数量")
            fig_pool.update_layout(height=360, margin=dict(l=10, r=10, t=20, b=70))
            st.plotly_chart(fig_pool, use_container_width=True)
            st.dataframe(industry_count, use_container_width=True, hide_index=True)
        except Exception as exc:  # noqa: BLE001
            st.warning(f"TOP30 行业分布读取失败：{exc}")


def extract_section(markdown: str, start_pattern: str, end_patterns: list[str]) -> str:
    start = re.search(start_pattern, markdown)
    if not start:
        return "报告中未找到该部分。"
    end_index = len(markdown)
    for pattern in end_patterns:
        match = re.search(pattern, markdown[start.end() :])
        if match:
            end_index = min(end_index, start.end() + match.start())
    return markdown[start.start() : end_index].strip()


def report_options(top_n: int = 5) -> dict[str, Path | None]:
    try:
        top_pool = read_csv(WEEK4_DATA / "final_top30_stock_pool.csv", dtype={"symbol": str})
    except Exception:
        return {}

    options: dict[str, Path | None] = {}
    for _, row in top_pool.sort_values("rank").head(top_n).iterrows():
        symbol = str(row["symbol"]).zfill(6)
        name = str(row["name"])
        rank = int(row["rank"])
        label = f"第{rank}名 {symbol} {name}"
        path = WEEK5_OUTPUTS / f"{symbol}_{name}_report.md"
        options[label] = path if path.exists() else None
    return options


def render_ai_research() -> None:
    st.title("🤖 AI投研")
    st.caption("对应 Week5：个股深度分析、趋势判断、市场情绪。")
    summary_path = WEEK5_DIR / "stock_deep_report.md"
    st.caption(f"汇总报告更新时间：{format_file_time(summary_path)}")

    options = report_options(top_n=5)
    if not options:
        st.error("没有找到 Week4 TOP 股票池，请先生成因子选股结果。")
        return

    selected = st.selectbox("选择股票研报", list(options.keys()))
    report_path = options[selected]
    if report_path is None:
        st.warning("该股票当前还没有生成 Week5 LLM 研报，请先在设置页运行快速刷新。")
        return
    report_text = report_path.read_text(encoding="utf-8")

    tab_full, tab_trend, tab_sentiment, tab_summary = st.tabs(
        ["个股深度分析", "趋势判断", "市场情绪", "汇总报告预览"]
    )
    with tab_full:
        st.markdown(report_text)
    with tab_trend:
        st.markdown(
            extract_section(
                report_text,
                r"##\s+\d+、中长期趋势判断框架（TrendAgent）",
                [r"##\s+\d+、市场情绪分析（SentimentAgent）", r"##\s+\d+、综合决策"],
            )
        )
    with tab_sentiment:
        st.markdown(
            extract_section(
                report_text,
                r"##\s+\d+、市场情绪分析（SentimentAgent）",
                [r"##\s+\d+、综合决策", r"## 附："],
            )
        )
    with tab_summary:
        if summary_path.exists():
            summary = summary_path.read_text(encoding="utf-8")
            st.markdown(summary[:12000])
            if len(summary) > 12000:
                st.info("汇总报告较长，当前仅预览前 12000 个字符。")
        else:
            st.warning("汇总报告不存在。")


def call_ak_function(fn_name: str, args: tuple[object, ...] = ()) -> pd.DataFrame:
    require_akshare()
    func = getattr(ak, fn_name)
    result = func(*args)
    if not isinstance(result, pd.DataFrame):
        raise RuntimeError(f"{fn_name} 返回结果不是 DataFrame")
    if result.empty:
        raise RuntimeError(f"{fn_name} 返回空表")
    result = result.copy()
    result["数据源"] = f"AkShare {fn_name}"
    return result


@st.cache_data(ttl=300)
def load_northbound_fund_data() -> tuple[pd.DataFrame, str]:
    candidates: list[tuple[str, tuple[object, ...]]] = [
        ("stock_hsgt_fund_flow_summary_em", ()),
        ("stock_hsgt_hist_em", ()),
        ("stock_hsgt_fund_min_em", ("北向资金",)),
    ]
    errors: list[str] = []
    for fn_name, args in candidates:
        try:
            return call_ak_function(fn_name, args), fn_name
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fn_name}: {exc}")
    raise RuntimeError("；".join(errors))


@st.cache_data(ttl=300)
def load_main_fund_data() -> tuple[pd.DataFrame, str]:
    candidates: list[tuple[str, tuple[object, ...]]] = [
        ("stock_main_fund_flow", ()),
        ("stock_market_fund_flow", ()),
        ("stock_fund_flow_individual", ("即时",)),
    ]
    errors: list[str] = []
    for fn_name, args in candidates:
        try:
            return call_ak_function(fn_name, args), fn_name
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fn_name}: {exc}")
    raise RuntimeError("；".join(errors))


def preferred_columns(df: pd.DataFrame) -> list[str]:
    keywords = [
        "代码",
        "名称",
        "日期",
        "时间",
        "资金",
        "净流入",
        "流入",
        "流出",
        "买入",
        "卖出",
        "涨跌幅",
        "最新",
        "收盘",
        "数据源",
    ]
    selected = [col for col in df.columns if any(keyword in str(col) for keyword in keywords)]
    return selected[:12] if selected else list(df.columns[:12])


def render_data_quality(df: pd.DataFrame, title: str) -> None:
    empty_ratio = df.isna().mean().sort_values(ascending=False)
    high_empty = empty_ratio[empty_ratio >= 0.5]
    st.caption(f"{title}：共 {len(df)} 行、{len(df.columns)} 列。")
    if not high_empty.empty:
        st.warning(
            "接口返回字段不完整/空值较多，当前仅作数据可用性观察。"
            f"空值率较高字段：{', '.join(high_empty.index.astype(str)[:8])}"
        )
    with st.expander(f"{title}字段空值比例"):
        quality_df = pd.DataFrame(
            {"字段": empty_ratio.index.astype(str), "空值比例": empty_ratio.values}
        )
        st.dataframe(quality_df, use_container_width=True, hide_index=True)


def render_fund_monitor() -> None:
    st.title("💰 资金监控")
    st.caption("主力资金使用实时/近实时接口优先；接口失败时显示错误信息。")

    st.subheader("主力资金")
    try:
        df, fn_name = load_main_fund_data()
        st.caption(f"接口：{fn_name}。共 {len(df)} 行、{len(df.columns)} 列。")
        st.dataframe(df[preferred_columns(df)].head(30), use_container_width=True, hide_index=True)
    except Exception as exc:  # noqa: BLE001
        st.error(f"主力资金实时接口获取失败：{exc}")


def run_step(label: str, command: list[str], env: dict[str, str] | None = None) -> bool:
    st.write(f"正在执行：{label}")
    with st.expander(f"命令：{label}", expanded=True):
        st.code(" ".join(command), language="bash")
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.stdout:
            st.text(result.stdout[-6000:])
        if result.stderr:
            st.error(result.stderr[-6000:])
        if result.returncode != 0:
            st.error(f"{label} 失败，退出码：{result.returncode}")
            return False
        st.success(f"{label} 完成")
        return True


def python_cmd() -> list[str]:
    return [sys.executable]


@st.cache_resource(show_spinner=False)
def ensure_industry_rotation_data(max_age_hours: int = 24) -> tuple[bool, str]:
    """启动看板时确保行业轮动 CSV 已生成。

    Streamlit 会在交互时反复 rerun 脚本，因此这里用 cache_resource 控制为
    当前服务进程只检查/刷新一次，避免每次点击都重抓 31 个行业历史行情。
    """

    path = WEEK6_DATA / "industry_rotation.csv"
    should_refresh = not path.exists()
    if path.exists():
        updated_at = datetime.fromtimestamp(path.stat().st_mtime)
        age_hours = (datetime.now() - updated_at).total_seconds() / 3600
        should_refresh = age_hours > max_age_hours

    if not should_refresh:
        return True, "行业轮动数据已存在，启动时无需刷新。"

    result = subprocess.run(
        python_cmd() + ["week6/industry_rotation.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "未知错误"
        return False, f"行业轮动自动刷新失败：{message[-1200:]}"
    return True, "行业轮动数据已在启动时自动刷新。"


def llm_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("LLM_API_KEY_ENV", "DEEPSEEK_API_KEY")
    env.setdefault("LLM_BASE_URL", "https://api.deepseek.com/chat/completions")
    env.setdefault("LLM_MODEL", "deepseek-reasoner")
    return env


def run_quick_refresh(top_n: int, backend: str) -> None:
    st.cache_data.clear()
    industry_mapping_top_n = max(top_n, 30)
    steps = [
        ("生成 Week4 最终因子产物", python_cmd() + ["week4/factor_system.py"]),
        ("生成申万一级行业映射", python_cmd() + ["week5/build_industry_mapping.py", "--top-n", str(industry_mapping_top_n)]),
        ("抓取市场情绪文本", python_cmd() + ["week5/market_sentiment_fetcher.py", "--top-n", str(top_n)]),
        ("刷新行业轮动", python_cmd() + ["week6/industry_rotation.py"]),
        (
            "运行 Week5 LLM 多 Agent",
            python_cmd()
            + ["week5/multi_agent_system.py", "--top-n", str(top_n), "--backend", backend],
        ),
    ]
    for label, command in steps:
        env = llm_env() if "LLM" in label else None
        if not run_step(label, command, env=env):
            return
    st.success("快速刷新全部完成。")


def run_full_refresh(end_date: str, top_n: int, backend: str) -> None:
    st.cache_data.clear()
    industry_mapping_top_n = max(top_n, 30)
    steps = [
        ("更新沪深300股票池", python_cmd() + ["week4/build_hs300_universe.py"]),
        (
            "完整重抓沪深300原始因子",
            python_cmd()
            + [
                "week4/factor_ranking.py",
                "--refresh",
                "--end-date",
                end_date,
                "--universe",
                "week4/data/hs300_universe.csv",
                "--output",
                "week4/data/hs300_factor_raw.csv",
                "--errors",
                "week4/data/hs300_factor_errors.csv",
                "--cache-dir",
                "week4/data/cache",
            ],
        ),
        (
            "生成 Week4 最终因子产物",
            python_cmd()
            + [
                "week4/factor_system.py",
                "--raw",
                "week4/data/hs300_factor_raw.csv",
            ],
        ),
        ("生成申万一级行业映射", python_cmd() + ["week5/build_industry_mapping.py", "--top-n", str(industry_mapping_top_n)]),
        ("抓取市场情绪文本", python_cmd() + ["week5/market_sentiment_fetcher.py", "--top-n", str(top_n)]),
        ("刷新行业轮动", python_cmd() + ["week6/industry_rotation.py"]),
        (
            "运行 Week5 LLM 多 Agent",
            python_cmd()
            + ["week5/multi_agent_system.py", "--top-n", str(top_n), "--backend", backend],
        ),
    ]
    for label, command in steps:
        env = llm_env() if "LLM" in label else None
        if not run_step(label, command, env=env):
            return
    st.success("完整重抓全部完成。")


def render_settings() -> None:
    st.title("⚙️ 设置")
    st.caption("数据更新、参数调整、文件状态检查。完整重抓耗时很长，课堂展示建议使用快速刷新。")

    top_n = st.number_input("AI投研股票数量 top_n_for_ai", min_value=1, max_value=30, value=5, step=1)
    backend = st.selectbox("LLM 后端", ["llm", "langchain"], index=0)
    default_end = datetime.now().strftime("%Y%m%d")
    end_date = st.text_input("完整重抓结束日期 full_refresh_end_date", value=default_end)

    col_fast, col_rotation, col_full = st.columns(3)
    with col_fast:
        if st.button("快速刷新", type="primary", use_container_width=True):
            run_quick_refresh(int(top_n), backend)
    with col_rotation:
        if st.button("刷新行业轮动", use_container_width=True):
            st.cache_data.clear()
            run_step("刷新行业轮动", python_cmd() + ["week6/industry_rotation.py"])
    with col_full:
        if st.button("完整重抓沪深300", use_container_width=True):
            run_full_refresh(end_date.strip(), int(top_n), backend)

    st.subheader("关键文件状态")
    status_paths = [
        WEEK4_DATA / "final_top30_stock_pool.csv",
        WEEK4_DATA / "final_factor_scores.csv",
        WEEK4_DATA / "final_factor_overview.csv",
        WEEK5_DIR / "industry_mapping.csv",
        WEEK5_DIR / "stock_deep_report.md",
        WEEK6_DATA / "industry_rotation.csv",
    ]
    status = [
        {
            "文件": str(path.relative_to(ROOT)),
            "是否存在": path.exists(),
            "更新时间": format_file_time(path),
            "大小KB": round(path.stat().st_size / 1024, 2) if path.exists() else None,
        }
        for path in status_paths
    ]
    st.dataframe(pd.DataFrame(status), use_container_width=True, hide_index=True)

    with st.expander("运行说明"):
        st.markdown(
            """
            - 快速刷新适合展示：刷新实时行情缓存，重算 Week4 final 产物，并重跑 Week5 行业、情绪和 LLM 研报。
            - 完整重抓会重新请求沪深300成分、行情、财务和估值接口，耗时长且更依赖外部接口稳定性。
            - 如果 LLM API key 不可用，Week5 主流程会失败，不生成伪研报。
            """
        )


def main() -> None:
    rotation_ready, rotation_message = ensure_industry_rotation_data()

    st.sidebar.markdown(
        """
        <div class="sidebar-title">A股中长期<br>投研看板</div>
        <div class="sidebar-subtitle">Final<br>Week6 · 6.1 看板整合</div>
        """,
        unsafe_allow_html=True,
    )
    page = st.sidebar.radio(
        "导航",
        ["市场概览", "因子选股", "AI投研", "资金监控", "个股对比", "AI每日复盘", "行业轮动", "设置"],
        index=0,
    )
    st.sidebar.divider()
    if rotation_ready:
        st.sidebar.caption(rotation_message)
    else:
        st.sidebar.warning(rotation_message)
    st.sidebar.markdown(
        f"""
        <div class="sidebar-note">
        当前时间<br>
        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        <br><br>
        本看板用于课程学习和投研流程演示。<br>
        不构成投资建议。
        </div>
        """,
        unsafe_allow_html=True,
    )

    if page == "市场概览":
        render_market_overview()
    elif page == "因子选股":
        render_factor_selection()
    elif page == "AI投研":
        render_ai_research()
    elif page == "资金监控":
        render_fund_monitor()
    elif page == "个股对比":
        render_stock_compare()
    elif page == "AI每日复盘":
        render_daily_review()
    elif page == "行业轮动":
        render_industry_rotation()
    elif page == "设置":
        render_settings()


if __name__ == "__main__":
    main()
