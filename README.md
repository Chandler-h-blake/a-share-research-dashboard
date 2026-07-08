# AI驱动A股中长期投研看板

一个围绕 A 股中长期投研看板搭建的实习学习项目。项目按 6 周推进：从金融基础学习、A 股数据获取与处理、Streamlit 市场概览看板，到因子研究、多因子选股、LLM 多 Agent 投研，最终整合成一个完整的 A 股中长期投研看板。

本项目用于课程学习、实习任务和投研流程演示，不构成任何投资建议。

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

注意：北向资金接口可以返回数据，但部分字段存在大量空值或 0。

### Week 3：Streamlit 市场概览看板

已完成：

- `week3/dashboard_v1_static.py`：静态原型版
- `week3/dashboard_v1.py`：真实数据尝试版

看板 V1 包含 4 个模块：

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
- `week4/factor_system.py`：多因子打分系统主入口，生成看板用 final 文件
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

沪深300相关结果：

- `week4/data/hs300_universe.csv`：沪深300股票池
- `week4/data/hs300_factor_raw.csv`：沪深300原始因子表
- `week4/data/hs300_factor_scores.csv`：沪深300完整打分表
- `week4/data/hs300_top30_stock_pool.csv`：沪深300多因子 TOP30 股票池
- `week4/data/hs300_factor_errors.csv`：错误记录表

后续看板默认读取的 final 文件：

- `week4/data/final_factor_scores.csv`
- `week4/data/final_top30_stock_pool.csv`
- `week4/data/final_factor_weights.json`
- `week4/data/final_factor_overview.csv`

当前 final TOP5 为：

| 排名 | 代码 | 名称 | 综合得分 |
| ---: | --- | --- | ---: |
| 1 | 002558 | 巨人网络 | 1.9592 |
| 2 | 300308 | 中际旭创 | 1.5380 |
| 3 | 603986 | 兆易创新 | 1.4435 |
| 4 | 002466 | 天齐锂业 | 1.4064 |
| 5 | 002709 | 天赐材料 | 1.1896 |

最终因子权重如下：

| 因子 | 权重 | 说明 |
| --- | ---: | --- |
| 营收同比增长率 | 0.22 | 成长因子，权重最高 |
| 20 日动量 | 0.20 | 动量因子，反映近期走势 |
| ROE | 0.15 | 质量因子 |
| 净利润同比增长率 | 0.13 | 成长辅助因子 |
| 毛利率 | 0.10 | 盈利质量辅助因子 |
| 换手率变化 | 0.07 | 交易活跃度因子 |
| 60 日波动率 | 0.05 | 风险约束 |
| PE 分位数 | 0.04 | 估值约束 |
| PB 分位数 | 0.04 | 估值约束 |

### Week 5：LLM 多 Agent 个股投研

第五周在 Week4 多因子 TOP 股票池基础上，构建了 LLM 驱动的多 Agent 个股投研系统。

已完成：

- `week5/stock_context_builder.py`：个股研究材料包构建
- `week5/prompts.py`：多 Agent Prompt 模板
- `week5/llm_client.py`：OpenAI-compatible LLM 调用封装
- `week5/multi_agent_system.py`：多 Agent 主流程
- `week5/build_industry_mapping.py`：TOP 股票池申万行业映射
- `week5/market_sentiment_fetcher.py`：市场情绪文本抓取
- `week5/outputs/*.md`：单股 LLM 深度研报
- `week5/stock_deep_report.md`：TOP 股票汇总研报

多 Agent 角色包括：

- DataAgent：数据摘要
- FactorAgent：因子画像
- TechnicalAgent：技术面和量价状态
- FundamentalAgent：基本面质量和成长
- RiskAgent：风险识别
- TrendAgent：中长期趋势判断
- SentimentAgent：市场情绪分析
- DecisionAgent：综合决策

第五周的核心思路是：先由程序把 Week4 因子数据、行业映射、行情和情绪文本整理成结构化材料包，再交给不同角色的 LLM Agent 分工分析，最后汇总成个股深度研报。

当前已保留若干本地 Markdown 研报，因此即使没有 LLM API key，最终看板中的 AI 投研页仍可以展示已有报告。

### Week 6：最终看板整合与特色功能

第六周完成最终看板整合，主入口为：

```text
research_dashboard_final.py
```

最终看板侧边栏包括：

- 市场概览
- 因子选股
- AI投研
- 资金监控
- 个股对比
- AI每日复盘
- 行业轮动
- 设置

第六周新增三个特色功能：

#### 1. 个股对比

基于 Week4 final 因子结果，从 TOP30 股票池中选择 2-5 只股票，横向比较：

- 综合得分
- 排名
- 动量
- ROE
- 毛利率
- 营收增长
- 净利润增长
- PE/PB 分位数
- 60 日波动率

页面同时展示综合得分柱状图和五维因子贡献雷达图。

#### 2. AI每日复盘

自动收集看板已有结构化行情材料：

- 指数行情
- 行业涨跌
- 涨跌分布
- 成交额 TOP20
- 主力资金

用户点击按钮后，调用 DeepSeek Reasoner 生成市场复盘。Prompt 中要求只基于输入数据，不编造新闻、政策、公告或资金数据。

#### 3. 行业轮动

新增脚本：

```text
week6/industry_rotation.py
```

输出：

```text
week6/data/industry_rotation.csv
```

行业轮动脚本使用：

- `ak.sw_index_first_info()`：获取申万一级行业列表
- `ak.index_hist_sw()`：获取申万一级行业历史行情

计算内容：

- 近 1 月涨跌幅
- 近 3 月涨跌幅
- 近 1 月排名
- 近 3 月排名
- 轮动分类

轮动分类包括：

- 持续强势
- 短期转强
- 中期强势
- 持续走弱
- 震荡中性

开发中发现 `sw_index_first_info()` 返回的行业代码可能是 `801010.SI`，但 `index_hist_sw()` 需要 `801010`，因此脚本中增加了行业代码标准化逻辑。

最终看板启动时会自动检查 `week6/data/industry_rotation.csv`：

- 文件不存在时自动生成
- 文件超过 24 小时未更新时自动刷新
- 24 小时内已生成则不重复抓取

这样避免 Streamlit 页面每次 rerun 都去请求 31 个行业历史行情。

## 运行方式

当前使用 conda 环境：

```bash
conda activate a-stock-week2
```

安装依赖：

```bash
pip install -r requirements.txt
```

如果没有使用 requirements，也可以手动安装：

```bash
pip install akshare pandas streamlit plotly
```

### 运行最终看板

```bash
streamlit run research_dashboard_final.py
```

或指定端口：

```bash
streamlit run research_dashboard_final.py --server.headless true --server.port 8501
```

浏览器打开：

```text
http://localhost:8501
```

8501 不是必须端口。如果被占用，可以换成 8502：

```bash
streamlit run research_dashboard_final.py --server.headless true --server.port 8502
```

检查端口占用：

```bash
for p in {8501..8520}; do
  lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && echo "$p occupied" || echo "$p free"
done
```

### 运行第三周看板

```bash
streamlit run week3/dashboard_v1.py
```

如果真实数据接口临时失败，可以运行静态原型版：

```bash
streamlit run week3/dashboard_v1_static.py
```

### 生成沪深300股票池

```bash
python week4/build_hs300_universe.py
```

### 计算沪深300原始因子

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

### 生成沪深300多因子得分和 TOP30 股票池

```bash
python week4/factor_scoring.py \
  --input week4/data/hs300_factor_raw.csv \
  --scores week4/data/hs300_factor_scores.csv \
  --top week4/data/hs300_top30_stock_pool.csv \
  --top-n 30
```

### 生成最终看板用因子产物

```bash
python week4/factor_system.py \
  --raw week4/data/hs300_factor_raw.csv \
  --top-n 30
```

默认输出：

- `week4/data/final_factor_scores.csv`
- `week4/data/final_top30_stock_pool.csv`
- `week4/data/final_factor_weights.json`
- `week4/data/final_factor_overview.csv`

### 生成 Week5 行业映射

```bash
python week5/build_industry_mapping.py --top-n 30
```

默认输出：

- `week5/industry_mapping.csv`

这个文件用于修正 TOP 股票池中 `industry=unknown` 的问题。

### 生成 Week5 LLM 多 Agent 研报

需要先配置 LLM API key。例如使用 DeepSeek：

```bash
export LLM_API_KEY_ENV=DEEPSEEK_API_KEY
export LLM_BASE_URL=https://api.deepseek.com/chat/completions
export LLM_MODEL=deepseek-reasoner
export DEEPSEEK_API_KEY="你的 API Key"
```

运行：

```bash
python week5/multi_agent_system.py --top-n 5 --backend llm
```

默认输出：

- `week5/outputs/*_report.md`
- `week5/stock_deep_report.md`

如果没有 LLM API key，程序会失败，不生成伪研报。

### 生成 Week6 行业轮动数据

```bash
python week6/industry_rotation.py
```

默认输出：

- `week6/data/industry_rotation.csv`

最终看板启动时也会自动检查并生成该文件。

## 数据源说明

项目主要使用 AkShare 获取 A 股数据。AkShare 底层数据来自东方财富、新浪财经、申万、巨潮资讯等公开数据源。

由于免费公开接口可能存在网络波动、字段变化、限流或临时不可用的问题，当前代码中对部分模块设置了备用接口、缓存和错误提示。

不同页面的数据实时性不同：

| 页面 | 数据来源 | 实时性 |
| --- | --- | --- |
| 市场概览 | AkShare 实时/近实时接口 | 300 秒缓存 |
| 因子选股 | Week4 本地 final CSV | 本地文件 |
| AI投研 | Week5 本地 Markdown 研报 | 本地文件 |
| 资金监控 | AkShare 资金流接口 | 300 秒缓存 |
| 个股对比 | Week4 本地 final CSV | 本地文件 |
| AI每日复盘 | AkShare 结构化行情 + DeepSeek | 点击后生成 |
| 行业轮动 | Week6 行业轮动 CSV | 启动时检查/24 小时刷新 |
| 设置 | 本地脚本和状态检查 | 控制入口 |




## 项目总结

这个项目从基础金融知识和数据获取开始，逐步完成了 A 股行情处理、市场概览看板、多因子选股、因子验证、LLM 多 Agent 研报生成，并最终整合为一个可运行的 Streamlit 投研看板。

整个过程完整走通了：

```text
金融概念学习 -> 数据获取 -> 数据清洗 -> 因子计算 -> 因子打分 -> 股票池生成 -> LLM 研报 -> 看板展示 -> 数据刷新
```

最终系统既包含实时/近实时行情观察，也包含本地多因子模型结果，还包含 LLM 辅助分析和行业轮动模块，能够作为一个实习阶段的完整 AI 投研项目展示。
