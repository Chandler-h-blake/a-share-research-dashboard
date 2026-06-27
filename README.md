# AI驱动A股中长期投研看板

一个围绕 A 股中长期投研看板搭建的实习学习项目。当前已经推进到第 4 周：前 3 周完成了金融基础学习、A 股数据获取与处理、Streamlit 市场概览看板；第 4 周正在搭建因子研究与多因子选股模型。

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

### Week 4：因子研究与多因子选股模型

已完成：

- `week4/因子研究.md`：因子投资基础学习笔记
- `week4/factors.py`：A 股因子库和因子计算模块
- `week4/factor_ranking.py`：原始因子批量计算脚本
- `week4/factor_scoring.py`：多因子标准化、方向调整、加权打分和排名脚本
- `week4/build_hs300_universe.py`：沪深300股票池生成脚本
- `week4/validate_factor_data.py`：观察股票池数据获取验证脚本

当前因子模型已经落地 9 个原始因子：

- 动量：20 日动量、换手率变化
- 价值：PE 分位数、PB 分位数
- 质量：ROE、毛利率
- 成长：营收同比增长率、净利润同比增长率
- 波动：60 日年化波动率

当前已经完成两个范围的因子计算：

- 10 只观察股票池：已生成 `factor_raw.csv`、`factor_scores.csv`、`top_stock_pool.csv`
- 沪深300股票池：已生成 `hs300_factor_raw.csv`、`hs300_factor_scores.csv`、`hs300_top30_stock_pool.csv`

沪深300当前结果：

- `week4/data/hs300_universe.csv`：300 只股票
- `week4/data/hs300_factor_raw.csv`：300 只股票的原始因子表
- `week4/data/hs300_factor_scores.csv`：300 只股票的完整打分表
- `week4/data/hs300_top30_stock_pool.csv`：沪深300多因子 TOP30 股票池
- `week4/data/hs300_factor_errors.csv`：错误记录表，当前无失败记录
- `week4/data/final_factor_scores.csv`：后续看板默认读取的最终得分表
- `week4/data/final_top30_stock_pool.csv`：后续看板默认读取的最终 TOP30 股票池
- `week4/data/final_factor_weights.json`：最终因子权重配置
- `week4/data/final_factor_overview.csv`：因子说明、权重和回测验证指标汇总

当前沪深300 TOP5 为：

| 排名 | 代码 | 名称 | 综合得分 |
| ---: | --- | --- | ---: |
| 1 | 002558 | 巨人网络 | 1.0439 |
| 2 | 688111 | 金山办公 | 0.9814 |
| 3 | 300308 | 中际旭创 | 0.9433 |
| 4 | 002709 | 天赐材料 | 0.8581 |
| 5 | 600519 | 贵州茅台 | 0.8534 |

注意：当前多因子权重仍是第一版人工设定，结果主要用于验证“数据获取 -> 因子计算 -> 标准化 -> 加权打分 -> 股票池输出”的完整链路。后续还需要用 IC、分层回测和样本外验证来评估因子有效性。

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

生成沪深300股票池：

```bash
python week4/build_hs300_universe.py
```

计算沪深300原始因子：

```bash
python week4/factor_ranking.py \
  --universe week4/data/hs300_universe.csv \
  --output week4/data/hs300_factor_raw.csv \
  --errors week4/data/hs300_factor_errors.csv \
  --cache-dir week4/data/cache
```

如果中途因为网络或接口问题失败，可以断点续跑：

```bash
python week4/factor_ranking.py \
  --universe week4/data/hs300_universe.csv \
  --output week4/data/hs300_factor_raw.csv \
  --errors week4/data/hs300_factor_errors.csv \
  --cache-dir week4/data/cache \
  --resume
```

生成沪深300多因子得分和 TOP30 股票池：

```bash
python week4/factor_scoring.py \
  --input week4/data/hs300_factor_raw.csv \
  --scores week4/data/hs300_factor_scores.csv \
  --top week4/data/hs300_top30_stock_pool.csv \
  --top-n 30
```

## 数据源说明

项目主要使用 AkShare 获取 A 股数据。AkShare 底层数据来自东方财富、新浪财经、申万等公开数据源。

由于免费公开接口可能存在网络波动、字段变化、限流或临时不可用的问题，当前代码中对部分模块设置了备用接口和静态备用数据。

## 后续计划

接下来计划继续推进：

- 增加factor_system.py模块，作为第四周程序主入口
- 根据因子有效性结果调整多因子权重
- 将多因子 TOP30、行业分布和因子贡献接入投研看板
