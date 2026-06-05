# Finance MCP — Claude Desktop

Investment Banking & Equity Research toolkit for Claude Desktop.
Modeled on **[anthropics/financial-services](https://github.com/anthropics/financial-services)** architecture.

---

## Architecture

Three MCP servers work together in Claude Desktop:

```
finance-mcp/
├── server.js                              ← IB & Equity Research tools (Node.js)
├── services/
│   ├── market-data/
│   │   ├── server.py                      ← Live market data (Python)
│   │   └── DATA_SOURCES.md               ← Notes on yfinance, AKShare & THS scraper
│   └── portfolio/
│       └── server.py                      ← Analysis log & position tracking (Python)
├── utils/
│   └── formatting.py                      ← Shared formatting helpers (imported by market-data)
├── skills/                                ← SKILL.md files for each IB/ER tool
│   ├── competitive-analysis/
│   ├── comps-table/
│   ├── dcf-model/
│   ├── earnings-snapshot/
│   ├── football-field/
│   ├── ic-memo/
│   ├── lbo-model/
│   ├── merger-accretion-dilution/
│   ├── one-pager/
│   ├── pitch-deck/
│   └── wacc-calculator/
├── README.md
└── package.json
```

---

## Tool Directory

### 📊 Live Market Data — `services/market-data/server.py`

#### Data Source Reference
| Tool | Description |
|---|---|
| `data_sources` | Full explanation of yfinance, AKShare, and the THS scraper — what each covers, limitations, and when to use each |

#### yfinance Tools — Global Markets (US, EU, HK)
> Free · No API key · Unofficial Yahoo Finance wrapper · Personal/research use only
> ⚠️ Subject to Yahoo rate limits. If a call fails, fall back to `web_search` for the price.

| Tool | Description |
|---|---|
| `yf_quote` | Live quote, valuation multiples, margins, analyst target for any global ticker |
| `yf_financials` | Income statement, balance sheet, or cash flow (annual or quarterly) |
| `yf_price_history` | Historical OHLCV prices with period and interval selection |
| `yf_peers_comps` | Pull multiples for a list of tickers simultaneously — feeds directly into `comps_table`. ⚠️ Does not normalise currencies across markets |
| `yf_analyst_estimates` | Consensus EPS, revenue estimates, price targets, buy/hold/sell recommendation |
| `yf_earnings_calendar` | Next earnings date and recent actuals vs. estimates |

#### AKShare Tools — China Markets (Macro, Indexes, Sector PE)
> Free · No API key · Open-source · Research use only

| Tool | Status | Description |
|---|---|---|
| `ak_a_share_financials` | ✅ Works | Multi-year financial statements from CSRC filings via Tonghuashun |
| `ak_macro_china` | ✅ Works | GDP, CPI, PPI, M2, PMI, retail sales, industrial output, trade balance |
| `ak_index_quote` | ✅ Works | CSI 300, CSI 500, SSE, SZSE, ChiNext, STAR Market levels |
| `ak_sector_pe` | ✅ Works | Current sector P/E ratios for Shanghai or Shenzhen exchange |
| ~~`ak_a_share_quote`~~ | ❌ Disabled | Blocked by MCP proxy (push2.eastmoney.com → ProxyError). Use `ak_a_share_quote_ths` instead |
| ~~`ak_a_share_history`~~ | ❌ Disabled | Blocked by MCP proxy (push2his.eastmoney.com → ProxyError). Handler preserved in code for future re-enabling |

#### Tonghuashun Scraper — A-Share Fundamentals (10jqka.com.cn)
> Scrapes Tonghuashun directly. Not blocked by MCP proxy. ✅

| Tool | Description |
|---|---|
| `ak_a_share_quote_ths` | Fetches EPS, NAV/share, net profit, revenue, profit growth, analyst consensus (last 60 trading days), recent block trades, and margin balance data for any A-share. **Does not return live intraday price** — use `web_search("600519 股价 今日")` for that |

---

### 📁 Portfolio & Analysis Log — `services/portfolio/server.py`

Persistent local storage for analysis conclusions, position tracking, and cost basis.
Zero dependency on market data — reads/writes a local `analysis_log.json` file.
Log path is overridable via the `PORTFOLIO_LOG_PATH` environment variable.

| Tool | When to Call | Description |
|---|---|---|
| `analysis_log_read` | **Start** of every analysis session | Retrieve prior conclusion, cost basis, stop loss, position type for a stock. Omit symbol to get full portfolio summary |
| `analysis_log_save` | **End** of every analysis session | Persist conclusion, price at analysis, cost basis, position type (底仓/卫星仓/观察/空仓), stop loss, target price, and notes |
| `analysis_log_delete` | When a position is closed | Remove a stock from the log |

Entries carry `schema_version` for forward-compatible migrations as new fields are added.

---

### 🏦 IB & Equity Research Tools — `server.js`

#### Competitive Intelligence
| Tool | Description |
|---|---|
| `competitive_analysis` | Strategic landscape: market structure, moats, growth quality, disruption risk |

#### Equity Research
| Tool | Slash | Description |
|---|---|---|
| `comps_table` | /comps | Trading comps table with mean/median benchmarks |
| `dcf_model` | /dcf | 5-year DCF + WACC × terminal growth sensitivity |
| `earnings_snapshot` | /earnings | Beat/miss analysis + guidance + investor questions |
| `one_pager` | /one-pager | Company tearsheet / profile |

#### Investment Banking
| Tool | Slash | Description |
|---|---|---|
| `pitch_deck_outline` | /pitch | Full pitch scaffold (M&A, IPO, Debt, Restructuring) |
| `merger_accretion_dilution` | /merger-ad | EPS accretion/dilution analysis |
| `lbo_model` | /lbo | IRR / MOIC returns matrix across exit multiples |
| `ic_memo_template` | /ic-memo | Investment Committee memo template |

#### Utilities
| Tool | Description |
|---|---|
| `wacc_calculator` | WACC from CAPM + after-tax cost of debt |
| `football_field` | Valuation range across methodologies |
| `list_tools` | Lists all IB/ER tools |

---

## Data Sources

| | yfinance | AKShare | THS Scraper |
|---|---|---|---|
| Coverage | Global (US, EU, HK, JP…) | China macro, indexes, sector PE | China A-share fundamentals |
| API key | ❌ None | ❌ None | ❌ None |
| Cost | Free | Free | Free |
| Live price | ✅ (rate-limited) | ❌ Eastmoney blocked | ❌ JS-rendered, not captured |
| Financials | ✅ Global | ✅ CSRC filings | ✅ THS page |
| Best for | US/EU/HK research | Macro context, index levels | A-share fundamentals + analyst data |

**For live A-share price:** use `web_search("600519 股价 今日")` — fastest and most reliable.

---

## Recommended Session Flow — A-Share Analysis

```
SESSION START
  1. analysis_log_read(symbol)        ← check prior conclusion, cost basis, stop loss
  2. ak_a_share_quote_ths(symbol)     ← fundamentals, analyst ratings, block trades, margin
  3. ak_a_share_financials(symbol)    ← multi-year CSRC filing data
  4. web_search("symbol 股价 今日")    ← live intraday price

SESSION END
  5. analysis_log_save(symbol, ...)   ← persist today's conclusion
```

---

## Installation

### 1. Install Node.js dependencies
```bash
cd ~/Desktop/mcp-servers/finance-mcp
npm install
```

### 2. Install Python dependencies
```bash
pip install yfinance akshare mcp
```

### 3. Configure Claude Desktop

Open `~/Library/Application Support/Claude/claude_desktop_config.json` and add all three servers:

```json
{
  "mcpServers": {
    "finance-mcp": {
      "command": "node",
      "args": ["/Users/YOUR_USERNAME/Desktop/mcp-servers/finance-mcp/server.js"]
    },
    "finance-market-data": {
      "command": "python3",
      "args": ["/Users/YOUR_USERNAME/Desktop/mcp-servers/finance-mcp/services/market-data/server.py"]
    },
    "finance-portfolio": {
      "command": "python3",
      "args": ["/Users/YOUR_USERNAME/Desktop/mcp-servers/finance-mcp/services/portfolio/server.py"]
    }
  }
}
```

Replace `YOUR_USERNAME` with your macOS username.

### 4. Restart Claude Desktop

---

## Example Workflows

### A-share deep dive with session memory
```
分析贵州茅台 (600519)，结合近期走势给出投资建议
```
Claude will: `analysis_log_read(600519)` → `ak_a_share_quote_ths` → `ak_a_share_financials` → `web_search` for price → analysis → `analysis_log_save`

### Auto-populate a comps table from live data
```
Pull live multiples for CRM, NOW, WDAY — then build a comps table.
```
Claude will: `yf_peers_comps` → `comps_table`

### DCF with live inputs
```
Pull the latest financials for MSFT and run a DCF.
Use 10% WACC and 2.5% terminal growth.
```
Claude will: `yf_quote` + `yf_financials` → `dcf_model`

### China macro context
```
Analyse the macro backdrop for Chinese consumer stocks —
include CPI, retail sales, and PMI.
```
Claude will: `ak_macro_china(cpi)` + `ak_macro_china(retail_sales)` + `ak_macro_china(pmi_manufacturing)`

### Cross-border comps
```
Build a comps table for a Chinese EV company against BYD, NIO, Li Auto, Tesla, and Rivian.
```
Claude will: `ak_a_share_quote_ths` (BYD) + `yf_peers_comps` (NIO, LI, TSLA, RIVN) → `comps_table`

### Portfolio review
```
Show me all my tracked stocks and their current conclusions.
```
Claude will: `analysis_log_read()` (no symbol — returns full portfolio summary table)

---

## Common A-Share Codes

| Company | 公司 | Symbol |
|---|---|---|
| Kweichow Moutai | 贵州茅台 | 600519 |
| Wuliangye | 五粮液 | 000858 |
| BYD | 比亚迪 | 002594 |
| CATL | 宁德时代 | 300750 |
| Hengrui Medicine | 恒瑞医药 | 600276 |
| Ping An Insurance | 中国平安 | 601318 |
| China Merchants Bank | 招商银行 | 600036 |
| Midea Group | 美的集团 | 000333 |
| SMIC | 中芯国际 | 688981 |
| Advanced Micro-Fab (AMEC) | 中微公司 | 688012 |
| Choho Industrial | 征和工业 | 003033 |
| LONGi Green Energy | 隆基绿能 | 601012 |

## Common Global Tickers

| Company | Ticker |
|---|---|
| Apple | AAPL |
| Microsoft | MSFT |
| NVIDIA | NVDA |
| Tencent (HK) | 0700.HK |
| Alibaba (HK) | 9988.HK |
| TSMC | TSM |
| Samsung | 005930.KS |
| BYD (HK) | 1211.HK |

---

## Credits

Skills framework and example skills are based on Anthropic's original work.
Original skills repository: https://github.com/anthropics/claude-skills

---

## Disclaimer

> Nothing produced by this server constitutes investment, legal, tax, or accounting advice.
> Outputs are analytical drafts for review by a qualified professional.
> Data from yfinance, AKShare, and Tonghuashun is for research purposes only —
> always verify against audited financials and institutional-grade data sources
> (Bloomberg, Wind, FactSet) before use in client materials or investment decisions.
