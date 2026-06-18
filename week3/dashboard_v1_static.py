import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


st.set_page_config(
    page_title="A股中长期投研看板 V1",
    layout="wide",
)


def render_index_overview():
    """模块1：指数概览。"""
    st.header("模块1：指数概览")

    index_data = pd.DataFrame({
        "指数": ["上证指数", "深证成指", "创业板指", "科创50"],
        "点位": [3050.12, 9800.55, 1900.33, 880.20],
        "涨跌幅": [0.85, 1.20, -0.35, 0.42],
        "成交额": [4200, 5300, 2100, 780],
    })

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

    st.plotly_chart(fig, use_container_width=True)


def render_industry_heatmap():
    """模块2：行业热力图。"""
    st.header("模块2：行业热力图")

    industry_data = pd.DataFrame({
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
        height=520,
        xaxis=dict(visible=False, constrain="domain"),
        yaxis=dict(visible=False, autorange="reversed"),
        margin=dict(l=10, r=10, t=20, b=10),
    )

    st.plotly_chart(fig_heatmap, use_container_width=True)


def render_market_distribution():
    """模块3：涨跌分布。"""
    st.header("模块3：涨跌分布")

    distribution_data = pd.DataFrame({
        "类型": ["上涨", "下跌", "平盘", "涨停", "跌停", "涨幅>5%", "跌幅<-5%"],
        "数量": [2341, 1876, 312, 68, 24, 186, 95],
    })

    col1, col2, col3 = st.columns(3)

    col1.metric("上涨家数", "2341")
    col2.metric("下跌家数", "1876")
    col3.metric("平盘家数", "312")

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
        xaxis_title="类型",
        yaxis_title="股票数量",
    )

    st.plotly_chart(fig_distribution, use_container_width=True)

def render_top_amount():
    """模块4：成交额 TOP20。"""
    st.header("模块4：成交额 TOP20")

    top_amount_data = pd.DataFrame({
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
        xaxis_title="股票名称",
        yaxis_title="成交额（亿元）",
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
