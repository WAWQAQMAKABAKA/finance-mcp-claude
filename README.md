# Finance MCP

A finance-focused Model Context Protocol (MCP) server built on top of Anthropic's skills framework.

This project leverages Claude's skill system to provide financial analysis capabilities including 
DCF modeling, LBO analysis, comparable company analysis, and market data retrieval.

## Credits

Skills framework and example skills are based on Anthropic's original work.
Original skills repository: https://github.com/anthropics/claude-skills (verify this URL)

## Getting Started

\```bash
npm install
\```

---

## 数据源说明 / Data Source Reference

| English | 中文 | Tool |
|---|---|---|
| Explain the data sources | 解释数据来源 | `data_sources` |

---

## yfinance — 全球市场 / Global Markets

| English | 中文 | Tool |
|---|---|---|
| Get me a live quote for AAPL | 获取苹果公司实时报价 | `yf_quote` |
| Show me annual income statement for MSFT | 显示微软年度损益表 | `yf_financials` |
| Show me quarterly balance sheet for GOOGL | 显示谷歌季度资产负债表 | `yf_financials` |
| Show me 1 year price history for TSLA | 显示特斯拉一年价格历史 | `yf_price_history` |
| Pull live multiples for CRM, NOW, WDAY | 获取CRM、NOW、WDAY的实时估值倍数 | `yf_peers_comps` |
| Get analyst estimates for NVDA | 获取英伟达分析师预测 | `yf_analyst_estimates` |
| When does Apple report earnings | 苹果公司下次财报发布日期 | `yf_earnings_calendar` |

---

## AKShare — 中国市场 / China Markets

| English | 中文 | Tool |
|---|---|---|
| Get me a quote for BYD, symbol 002594 | 获取比亚迪实时报价，代码002594 | `ak_a_share_quote` |
| Show me 6 months price history for Moutai 600519 | 显示茅台六个月价格历史，代码600519 | `ak_a_share_history` |
| Get financials for CATL, symbol 300750 | 获取宁德时代财务数据，代码300750 | `ak_a_share_financials` |
| Show me China CPI data | 显示中国CPI数据 | `ak_macro_china` |
| Show me China GDP data | 显示中国GDP数据 | `ak_macro_china` |
| Show me China manufacturing PMI | 显示中国制造业PMI | `ak_macro_china` |
| Show me China M2 money supply | 显示中国M2货币供应量 | `ak_macro_china` |
| Show me China PPI data | 显示中国PPI数据 | `ak_macro_china` |
| Show me China retail sales | 显示中国零售销售数据 | `ak_macro_china` |
| Show me China trade balance | 显示中国贸易差额 | `ak_macro_china` |
| What is the CSI 300 at | 沪深300指数现在是多少 | `ak_index_quote` |
| Show me the SSE composite index | 显示上证综合指数 | `ak_index_quote` |
| Show me ChiNext index | 显示创业板指数 | `ak_index_quote` |
| Show me STAR Market index | 显示科创50指数 | `ak_index_quote` |
| Show me sector P/E for Shanghai exchange | 显示上交所各行业市盈率 | `ak_sector_pe` |
| Show me sector P/E for Shenzhen exchange | 显示深交所各行业市盈率 | `ak_sector_pe` |

---

## 竞争分析 / Competitive Intelligence

| English | 中文 | Tool |
|---|---|---|
| Analyze the competitive landscape for cloud infrastructure | 分析云计算基础设施的竞争格局 | `competitive_analysis` |
| Competitive analysis of Chinese EV makers, deep dive | 深度分析中国电动车行业竞争格局 | `competitive_analysis` |
| Brief competitive overview of the SaaS sector | 简要分析SaaS行业竞争概况 | `competitive_analysis` |

---

## 股票研究 / Equity Research

| English | 中文 | Tool |
|---|---|---|
| Build a comps table for Salesforce vs peers | 建立Salesforce与同行的可比公司分析表 | `comps_table` |
| Run a DCF on a SaaS company | 对SaaS公司进行DCF估值分析 | `dcf_model` |
| Earnings snapshot for Apple Q1 2025 | 生成苹果2025年第一季度财报快照 | `earnings_snapshot` |
| Give me a one-pager on Tesla | 生成特斯拉一页纸公司简报 | `one_pager` |

---

## 投资银行 / Investment Banking

| English | 中文 | Tool |
|---|---|---|
| Build a sell-side M&A pitch for a SaaS company | 为SaaS公司建立出售方并购推介材料 | `pitch_deck_outline` |
| Build a buy-side M&A pitch | 建立买方并购推介材料 | `pitch_deck_outline` |
| Build an IPO pitch for a fintech company | 为金融科技公司建立IPO推介材料 | `pitch_deck_outline` |
| Run an LBO on a company with $1.2B EV | 对企业价值12亿美元的公司进行LBO分析 | `lbo_model` |
| Merger accretion dilution analysis | 并购摊薄增厚分析 | `merger_accretion_dilution` |
| Generate an IC memo for a growth equity deal | 生成成长型股权投资的投委会备忘录 | `ic_memo_template` |

---

## 工具类 / Utilities

| English | 中文 | Tool |
|---|---|---|
| Calculate WACC for a tech company | 计算科技公司的加权平均资本成本 | `wacc_calculator` |
| Build a football field valuation | 建立橄榄球场估值区间图 | `football_field` |
| List all available finance tools | 列出所有可用的金融工具 | `list_tools` |

---

## 🔗 组合使用 / Power Combos

| English | 中文 | Tools |
|---|---|---|
| Pull live multiples then build a comps table | 获取实时倍数后建立可比公司分析表 | `yf_peers_comps` → `comps_table` |
| Get financials then run a DCF | 获取财务数据后进行DCF分析 | `yf_financials` → `dcf_model` |
| Get BYD quote then write a one-pager | 获取比亚迪报价后生成公司简报 | `ak_a_share_quote` → `one_pager` |
| Show China macro data then write investment thesis | 显示中国宏观数据后撰写投资逻辑 | `ak_macro_china` → analysis |
| Pull earnings data then build earnings snapshot | 获取财报数据后生成财报快照 | `yf_earnings_calendar` + `yf_analyst_estimates` → `earnings_snapshot` |
| Cross-border comps — China vs US | 跨境可比公司分析——中美对比 | `ak_a_share_quote` + `yf_peers_comps` → `comps_table` |

---

## 常用A股代码 / Common A-Share Codes

| Company | 公司 | Symbol |
|---|---|---|
| Kweichow Moutai | 贵州茅台 | 600519 |
| BYD | 比亚迪 | 002594 |
| CATL | 宁德时代 | 300750 |
| Ping An Insurance | 中国平安 | 601318 |
| Industrial & Commercial Bank | 工商银行 | 601398 |
| China Merchants Bank | 招商银行 | 600036 |
| Alibaba (A-share) | 阿里巴巴 | 688688 |
| CITIC Securities | 中信证券 | 600030 |
| Midea Group | 美的集团 | 000333 |
| Wuliangye | 五粮液 | 000858 |
| LONGi Green Energy | 隆基绿能 | 601012 |
| Ping An Bank | 平安银行 | 000001 |

---

## 常用全球股票代码 / Common Global Tickers

| Company | 公司 | Ticker |
|---|---|---|
| Apple | 苹果 | AAPL |
| Microsoft | 微软 | MSFT |
| Google | 谷歌 | GOOGL |
| Amazon | 亚马逊 | AMZN |
| Tesla | 特斯拉 | TSLA |
| NVIDIA | 英伟达 | NVDA |
| Meta | Meta | META |
| Salesforce | Salesforce | CRM |
| ServiceNow | ServiceNow | NOW |
| Workday | Workday | WDAY |
| Samsung | 三星 | 005930.KS |
| TSMC | 台积电 | TSM |
| Alibaba (US) | 阿里巴巴 (美股) | BABA |
| Tencent (HK) | 腾讯 (港股) | 0700.HK |
| BYD (HK) | 比亚迪 (港股) | 1211.HK |

---

*Finance MCP — Built on anthropics/financial-services architecture*
*最后更新 / Last updated: May 2026*
