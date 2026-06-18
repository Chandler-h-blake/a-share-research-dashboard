# AI驱动A股中长期投研看板

一个围绕 A 股中长期投研看板搭建的实习学习项目。当前完成了第 1 周到第 3 周的内容：先补金融基础，再学习数据获取与处理，最后用 Streamlit 搭建市场概览看板

## 当前进度

### Week 1：A股基础学习

已完成：

- `week1/a_stock_basics.md`：A 股市场基础知识整理
- `week1/finance_glossary.md`：金融术语学习笔记
- `week1/stock_watchlist.md`：观察股票池 watchlist

主要理解 A 股基础概念、常见行情指标、K 线、技术指标、估值和资金面等内容。

### Week 2：数据获取与处理

已完成：

- `week2/data_fetcher.py`：A 股数据获取模块
- `week2/data_exploration.ipynb`：数据探索与处理 notebook

`data_fetcher.py` 当前包含：

- `get_daily_data()`：获取个股日线数据
- `get_index_data()`：获取指数日线数据
- `get_north_flow()`：获取北向资金相关数据
- `get_financial_data()`：获取个股财务摘要
- `clean_daily_data()`：基础数据清洗
- `add_basic_indicators()`：计算 MA5、MA20、日收益率、成交量均线等指标

第二周也完成了缺失值检查、异常值 Winsorize 缩尾、基础技术指标计算，以及部分个股的价格、均线、成交量可视化。

注意：北向资金接口可以返回数据，但部分字段存在大量空值或 0

### Week 3：Streamlit 市场概览看板

已完成：

- `week3/dashboard_v1_static.py`：静态原型版
- `week3/dashboard_v1.py`：真实数据尝试版

看板当前包含 4 个模块：

- 模块1：指数概览
- 模块2：行业热力图
- 模块3：涨跌分布
- 模块4：成交额 TOP20

其中 `dashboard_v1.py` 已经接入 AkShare 真实数据：

- 指数概览：优先东方财富指数接口，失败后使用新浪财经指数接口
- 行业热力图：优先申万一级行业接口，失败后使用东方财富行业板块接口
- 涨跌分布：基于全市场实时行情统计
- 成交额 TOP20：基于全市场实时行情排序

如果真实接口失败，页面会自动回退到静态备用数据，避免整个看板打不开。

## 运行方式

当前使用 conda 环境：

```bash
conda activate a-stock-week2
```

安装依赖：

```bash
pip install akshare pandas streamlit plotly
```

运行第三周看板：

```bash
streamlit run week3/dashboard_v1.py
```

如果真实数据接口临时失败，可以运行静态原型版：

```bash
streamlit run week3/dashboard_v1_static.py
```

## 数据源说明

项目主要使用 AkShare 获取 A 股数据。AkShare 底层数据来自东方财富、新浪财经、申万等公开数据源。

由于免费公开接口可能存在网络波动、字段变化、限流或临时不可用的问题，当前代码中对部分模块设置了备用接口和静态备用数据。

## 后续计划

接下来计划继续推进：

- 完善第三周看板截图和周报说明
- 优化看板布局和交互体验
- 在第 4 周开始学习因子研究和多因子选股模型
