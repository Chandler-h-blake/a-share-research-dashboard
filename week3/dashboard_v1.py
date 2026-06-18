import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

try:
    import akshare as ak
except ImportError:
    ak = None


st.set_page_config(
    page_title="A股中长期投研看板 V1",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 1rem;
        max-width: 96%;
    }
    h1 {
        font-size: 2rem !important;
        margin-bottom: 0.5rem !important;
    }
    h2 {
        font-size: 1.35rem !important;
        margin-top: 0.8rem !important;
        margin-bottom: 0.35rem !important;
    }
    h3 {
        font-size: 1.05rem !important;
        margin-top: 0.45rem !important;
        margin-bottom: 0.25rem !important;
    }
    [data-testid="stMetric"] {
        padding: 0.35rem 0.5rem;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.25rem;
    }
    [data-testid="stDataFrame"] {
        margin-top: 0.2rem;
        margin-bottom: 0.4rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_index_overview():
    """模块1：指数概览。"""
    st.header("模块1：指数概览")

    try:
        index_data = load_index_overview_data()
        data_source = index_data["数据源"].iloc[0]
        st.caption(f"数据来源：{data_source}。成交额单位：亿元。")
        index_data = index_data.drop(columns=["数据源"])
    except Exception as exc:
        st.warning(f"指数真实数据获取失败，暂时使用静态备用数据。错误信息：{exc}")
        index_data = get_static_index_overview_data()

    cols = st.columns(4)

    for i, row in index_data.iterrows():
        cols[i].metric(
            label=row["指数"],
            value=f'{row["点位"]:.2f}',
            delta=f'{row["涨跌幅"]:.2f}%',
        )

    st.subheader("指数数据表")
    st.dataframe(index_data, use_container_width=True)

    st.subheader("指数涨跌幅对比")

    fig = px.bar(
        index_data,
        x="指数",
        y="涨跌幅",
        color="涨跌幅",
        color_continuous_scale=["green", "red"],
        text="涨跌幅",
    )
    fig.update_layout(height=260, margin=dict(l=10, r=10, t=20, b=20))

    st.plotly_chart(fig, use_container_width=True)


def get_static_index_overview_data():
    """接口失败时使用的静态指数概览数据。"""
    return pd.DataFrame({
        "代码": ["000001", "399001", "399006", "000688"],
        "指数": ["上证指数", "深证成指", "创业板指", "科创50"],
        "点位": [3050.12, 9800.55, 1900.33, 880.20],
        "涨跌幅": [0.85, 1.20, -0.35, 0.42],
        "成交额": [4200, 5300, 2100, 780],
    })


@st.cache_data(ttl=300)
def load_index_overview_data():
    """获取主要指数实时行情。"""
    if ak is None:
        raise RuntimeError("当前环境没有安装 akshare")

    target_names = ["上证指数", "深证成指", "创业板指", "科创50"]
    errors = []

    try:
        raw_df = ak.stock_zh_index_spot_em(symbol="沪深重要指数")
        data_source = "AkShare stock_zh_index_spot_em / 东方财富"
    except Exception as em_error:
        errors.append(f"东方财富指数接口失败：{em_error}")

        try:
            raw_df = ak.stock_zh_index_spot_sina()
            data_source = "AkShare stock_zh_index_spot_sina / 新浪财经"
        except Exception as sina_error:
            errors.append(f"新浪指数接口失败：{sina_error}")
            raise RuntimeError("；".join(errors)) from sina_error

    required_columns = ["代码", "名称", "最新价", "涨跌幅", "成交额"]
    missing_columns = [col for col in required_columns if col not in raw_df.columns]

    if missing_columns:
        raise RuntimeError(f"指数接口返回结果缺少字段：{missing_columns}")

    result_df = raw_df[required_columns].copy()
    result_df = result_df[result_df["名称"].isin(target_names)].copy()

    if result_df.empty:
        raise RuntimeError("指数接口返回结果中没有找到上证指数、深证成指、创业板指、科创50")

    for col in ["最新价", "涨跌幅", "成交额"]:
        result_df[col] = pd.to_numeric(result_df[col], errors="coerce")

    result_df["成交额"] = result_df["成交额"] / 100000000
    result_df["数据源"] = data_source
    result_df = result_df.rename(columns={"名称": "指数", "最新价": "点位"})

    order_map = {name: index for index, name in enumerate(target_names)}
    result_df["排序"] = result_df["指数"].map(order_map)
    result_df = result_df.sort_values("排序").drop(columns=["排序"])

    return result_df.reset_index(drop=True)


def render_industry_heatmap():
    """模块2：行业热力图。"""
    st.header("模块2：行业热力图")

    try:
        industry_data = load_industry_heatmap_data()
        data_source = industry_data["数据源"].iloc[0]
        st.caption(f"数据来源：{data_source}。")
        industry_data = industry_data.drop(columns=["数据源"])
    except Exception as exc:
        st.warning(f"行业真实数据获取失败，暂时使用静态备用数据。错误信息：{exc}")
        industry_data = get_static_industry_heatmap_data()

    st.subheader("申万一级行业涨跌幅")

    rows = 4
    cols = 8
    padded_data = industry_data.copy()

    while len(padded_data) < rows * cols:
        padded_data.loc[len(padded_data)] = {"行业": "", "涨跌幅": None}

    z_values = []
    text_values = []

    for row_index in range(rows):
        row_slice = padded_data.iloc[row_index * cols:(row_index + 1) * cols]
        z_values.append(row_slice["涨跌幅"].tolist())
        text_values.append([
            f'{item["行业"]}<br>{item["涨跌幅"]:.2f}%'
            if pd.notna(item["涨跌幅"])
            else ""
            for _, item in row_slice.iterrows()
        ])

    fig_heatmap = go.Figure(
        data=go.Heatmap(
            z=z_values,
            text=text_values,
            texttemplate="%{text}",
            textfont={"size": 14},
            colorscale=[
                [0.0, "green"],
                [0.5, "white"],
                [1.0, "red"],
            ],
            zmin=-3,
            zmax=3,
            hovertemplate="%{text}<extra></extra>",
            colorbar=dict(title="涨跌幅"),
            showscale=True,
        )
    )

    fig_heatmap.update_layout(
        height=360,
        xaxis=dict(visible=False, constrain="domain"),
        yaxis=dict(visible=False, autorange="reversed"),
        margin=dict(l=10, r=10, t=20, b=10),
    )

    st.plotly_chart(fig_heatmap, use_container_width=True)


def get_static_industry_heatmap_data():
    """接口失败时使用的静态行业热力图数据。"""
    return pd.DataFrame({
        "行业": [
            "农林牧渔", "基础化工", "钢铁", "有色金属", "电子", "家用电器",
            "食品饮料", "纺织服饰", "轻工制造", "医药生物", "公用事业",
            "交通运输", "房地产", "商贸零售", "社会服务", "综合",
            "建筑材料", "建筑装饰", "电力设备", "国防军工", "计算机",
            "传媒", "通信", "银行", "非银金融", "汽车", "机械设备",
            "煤炭", "石油石化", "环保", "美容护理",
        ],
        "涨跌幅": [
            0.85, 1.26, -0.42, 2.18, 1.75, 0.66,
            -0.35, 0.28, -0.80, -1.15, 0.52,
            0.74, -1.62, -0.48, 1.05, 0.12,
            -0.95, 0.38, 2.46, 1.32, 1.88,
            -0.72, 0.94, -0.18, 0.41, 2.05, 1.14,
            -1.05, -0.56, 0.33, 0.69,
        ],
    })


@st.cache_data(ttl=300)
def load_industry_heatmap_data():
    """获取行业涨跌幅数据。"""
    if ak is None:
        raise RuntimeError("当前环境没有安装 akshare")

    errors = []

    try:
        raw_df = ak.index_realtime_sw(symbol="一级行业")
        required_columns = ["指数名称", "昨收盘", "最新价"]
        missing_columns = [col for col in required_columns if col not in raw_df.columns]

        if missing_columns:
            raise RuntimeError(f"申万接口返回结果缺少字段：{missing_columns}")

        result_df = raw_df[required_columns].copy()
        result_df["昨收盘"] = pd.to_numeric(result_df["昨收盘"], errors="coerce")
        result_df["最新价"] = pd.to_numeric(result_df["最新价"], errors="coerce")
        result_df["涨跌幅"] = (result_df["最新价"] - result_df["昨收盘"]) / result_df["昨收盘"] * 100
        result_df = result_df.rename(columns={"指数名称": "行业"})
        result_df = result_df[["行业", "涨跌幅"]].dropna(subset=["涨跌幅"])
        result_df["数据源"] = "AkShare index_realtime_sw / 申万一级行业"
        return result_df.head(31).reset_index(drop=True)
    except Exception as sw_error:
        errors.append(f"申万行业接口失败：{sw_error}")

    try:
        raw_df = ak.stock_board_industry_name_em()
        required_columns = ["板块名称", "涨跌幅"]
        missing_columns = [col for col in required_columns if col not in raw_df.columns]

        if missing_columns:
            raise RuntimeError(f"东方财富行业接口返回结果缺少字段：{missing_columns}")

        result_df = raw_df[required_columns].copy()
        result_df["涨跌幅"] = pd.to_numeric(result_df["涨跌幅"], errors="coerce")
        result_df = result_df.rename(columns={"板块名称": "行业"})
        result_df = result_df[["行业", "涨跌幅"]].dropna(subset=["涨跌幅"])
        result_df["数据源"] = "AkShare stock_board_industry_name_em / 东方财富行业板块"
        return result_df.head(31).reset_index(drop=True)
    except Exception as em_error:
        errors.append(f"东方财富行业接口失败：{em_error}")
        raise RuntimeError("；".join(errors)) from em_error


def get_static_market_distribution_data():
    """接口失败时使用的静态涨跌分布数据。"""
    return pd.DataFrame({
        "类型": ["上涨", "下跌", "平盘", "涨停", "跌停", "涨幅>5%", "跌幅<-5%"],
        "数量": [2341, 1876, 312, 68, 24, 186, 95],
    })


def build_market_distribution_data(market_df):
    """根据全市场实时行情计算涨跌分布。"""
    pct_change = pd.to_numeric(market_df["涨跌幅"], errors="coerce").dropna()

    return pd.DataFrame({
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
    })


def render_market_distribution():
    """模块3：涨跌分布。"""
    st.header("模块3：涨跌分布")

    try:
        market_df = load_market_spot_data()
        data_source = market_df["数据源"].iloc[0]
        st.caption(f"数据来源：{data_source}。基于全市场实时行情统计。")
        distribution_data = build_market_distribution_data(market_df)
    except Exception as exc:
        st.warning(f"真实数据获取失败，暂时使用静态备用数据。错误信息：{exc}")
        distribution_data = get_static_market_distribution_data()

    col1, col2, col3 = st.columns(3)

    distribution_map = dict(zip(distribution_data["类型"], distribution_data["数量"]))
    col1.metric("上涨家数", f'{distribution_map.get("上涨", 0)}')
    col2.metric("下跌家数", f'{distribution_map.get("下跌", 0)}')
    col3.metric("平盘家数", f'{distribution_map.get("平盘", 0)}')

    st.subheader("涨跌家数分布")

    fig_distribution = px.bar(
        distribution_data,
        x="类型",
        y="数量",
        color="类型",
        color_discrete_map={
            "上涨": "red",
            "下跌": "green",
            "平盘": "gray",
            "涨停": "darkred",
            "跌停": "darkgreen",
            "涨幅>5%": "orangered",
            "跌幅<-5%": "seagreen",
        },
        text="数量",
    )

    fig_distribution.update_layout(
        height=280,
        xaxis_title="类型",
        yaxis_title="股票数量",
        margin=dict(l=10, r=10, t=20, b=20),
    )

    st.plotly_chart(fig_distribution, use_container_width=True)


def get_static_top_amount_data():
    """接口失败时使用的静态备用数据。"""
    return pd.DataFrame({
        "代码": [
            "600519", "300750", "002594", "600036", "600900",
            "000858", "601318", "000333", "600887", "601899",
            "601398", "600030", "601012", "000651", "600276",
            "601888", "000001", "600309", "601668", "600000",
        ],
        "名称": [
            "贵州茅台", "宁德时代", "比亚迪", "招商银行", "长江电力",
            "五粮液", "中国平安", "美的集团", "伊利股份", "紫金矿业",
            "工商银行", "中信证券", "隆基绿能", "格力电器", "恒瑞医药",
            "中国中免", "平安银行", "万华化学", "中国建筑", "浦发银行",
        ],
        "涨跌幅": [
            1.20, -0.80, 2.35, 0.65, -0.20,
            1.05, -1.10, 0.88, 0.45, 3.20,
            0.15, -0.55, 2.10, 0.72, -0.95,
            1.66, -0.30, 2.80, 0.25, -0.40,
        ],
        "成交额": [
            85.2, 78.6, 72.4, 66.1, 58.7,
            55.3, 51.8, 48.6, 44.2, 42.9,
            40.1, 38.7, 36.5, 35.8, 34.4,
            33.9, 32.5, 31.7, 30.8, 29.6,
        ],
        "换手率": [
            0.45, 1.82, 2.35, 0.68, 0.22,
            0.76, 0.58, 0.91, 0.64, 3.15,
            0.08, 1.24, 2.10, 0.85, 0.72,
            1.66, 0.95, 1.88, 0.30, 0.42,
        ],
    })


@st.cache_data(ttl=300)
def load_market_spot_data():
    """获取全市场实时行情。"""
    if ak is None:
        raise RuntimeError("当前环境没有安装 akshare")

    errors = []

    try:
        raw_df = ak.stock_zh_a_spot_em()
        required_columns = ["代码", "名称", "涨跌幅", "成交额", "换手率"]
        missing_columns = [col for col in required_columns if col not in raw_df.columns]

        if missing_columns:
            raise RuntimeError(f"东方财富接口返回结果缺少字段：{missing_columns}")

        result_df = raw_df[required_columns].copy()
        data_source = "AkShare stock_zh_a_spot_em / 东方财富"
    except Exception as em_error:
        errors.append(f"东方财富接口失败：{em_error}")

        try:
            raw_df = ak.stock_zh_a_spot()
            required_columns = ["代码", "名称", "涨跌幅", "成交额"]
            missing_columns = [col for col in required_columns if col not in raw_df.columns]

            if missing_columns:
                raise RuntimeError(f"新浪接口返回结果缺少字段：{missing_columns}")

            result_df = raw_df[required_columns].copy()
            result_df["换手率"] = pd.NA
            data_source = "AkShare stock_zh_a_spot / 新浪财经"
        except Exception as sina_error:
            errors.append(f"新浪接口失败：{sina_error}")
            raise RuntimeError("；".join(errors)) from sina_error

    numeric_columns = ["涨跌幅", "成交额", "换手率"]

    for col in numeric_columns:
        result_df[col] = pd.to_numeric(result_df[col], errors="coerce")

    result_df = result_df.dropna(subset=["成交额"])
    result_df["成交额"] = result_df["成交额"] / 100000000
    result_df["数据源"] = data_source

    return result_df.reset_index(drop=True)


def load_top_amount_data():
    """获取全市场成交额 TOP20。"""
    market_df = load_market_spot_data()
    return market_df.sort_values("成交额", ascending=False).head(20).reset_index(drop=True)


def render_top_amount():
    """模块4：成交额 TOP20。"""
    st.header("模块4：成交额 TOP20")

    try:
        top_amount_data = load_top_amount_data()
        data_source = top_amount_data["数据源"].iloc[0]
        st.caption(f"数据来源：{data_source}。成交额单位：亿元。")
        top_amount_data = top_amount_data.drop(columns=["数据源"])
    except Exception as exc:
        st.warning(f"真实数据获取失败，暂时使用静态备用数据。错误信息：{exc}")
        top_amount_data = get_static_top_amount_data()

    top_amount_data = top_amount_data.sort_values("成交额", ascending=False).head(20)

    st.dataframe(
        top_amount_data,
        use_container_width=True,
    )

    st.subheader("成交额排名图")

    fig_top_amount = px.bar(
        top_amount_data,
        x="名称",
        y="成交额",
        color="涨跌幅",
        color_continuous_scale=["green", "red"],
        text="成交额",
    )

    fig_top_amount.update_layout(
        height=340,
        xaxis_title="股票名称",
        yaxis_title="成交额（亿元）",
        margin=dict(l=10, r=10, t=20, b=70),
    )

    fig_top_amount.update_xaxes(
        categoryorder="array",
        categoryarray=top_amount_data["名称"].tolist(),
    )

    st.plotly_chart(fig_top_amount, use_container_width=True)


st.title("A股中长期投研看板 V1")
render_index_overview()
render_industry_heatmap()
render_market_distribution()
render_top_amount()
