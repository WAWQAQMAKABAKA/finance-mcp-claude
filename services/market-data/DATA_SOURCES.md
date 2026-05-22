# Market Data Sources

This server integrates two open-source financial data libraries.
Neither requires an API key or paid subscription for basic use.

---

## 📊 yfinance

**What it is**
An open-source Python library that wraps Yahoo Finance's public APIs.
The most widely used free financial data tool in the Python ecosystem,
with an active maintainer community and regular releases.

**GitHub:** https://github.com/ranaroussi/yfinance
**Install:** `pip install yfinance`
**Latest:** v1.3.0 (April 2026)

**What it covers**
- Global equities: US (NYSE, NASDAQ), Europe, Hong Kong, Japan, and more
- Real-time quotes and key statistics (price, market cap, EV, beta)
- Historical OHLCV price data (daily, weekly, monthly)
- Financial statements: income statement, balance sheet, cash flow
- Valuation multiples: P/E, EV/EBITDA, EV/Revenue, P/B, P/S
- Analyst consensus: EPS estimates, revenue estimates, price targets, buy/hold/sell
- Earnings calendar: upcoming dates, historical actuals vs. estimates
- Options chains, dividends, stock splits

**Tools in this MCP that use yfinance**
| Tool | What it pulls |
|---|---|
| `yf_quote` | Live quote, multiples, margins, analyst target |
| `yf_financials` | Income statement, balance sheet, cash flow |
| `yf_price_history` | OHLCV historical prices |
| `yf_peers_comps` | Multiples for a list of tickers — ready for comps_table |
| `yf_analyst_estimates` | Consensus EPS, revenue, price targets |
| `yf_earnings_calendar` | Next earnings date, recent actuals vs. estimates |

**Limitations**
- ⚠️ **Unofficial** — not affiliated with or endorsed by Yahoo Inc.
- ⚠️ **Rate limits** — Yahoo rate-limits heavy or rapid use from the same IP.
  Works reliably for light MCP use (5–20 calls per session).
- ⚠️ **Fragility** — Yahoo occasionally changes internal API endpoints,
  which can break yfinance temporarily (usually fixed within days by maintainers).
- ⚠️ **Terms of service** — data is for personal/research use only per Yahoo's ToS.
  Not for commercial redistribution or client-facing use without independent verification.
- ⚠️ **China A-shares** — limited and unreliable coverage. Use AKShare instead.

**When to use it**
- US, European, or Hong Kong listed companies
- Auto-populating comps tables, DCF inputs, or one-pagers
- Pulling analyst consensus estimates for earnings analysis
- Checking price history or volatility

---

## 🇨🇳 AKShare

**What it is**
An open-source Python financial data library built specifically for Chinese
financial markets. Sources data from Eastmoney (东方财富), Sina Finance (新浪财经),
Tonghuashun (同花顺), and the National Bureau of Statistics of China.
Completely free — no registration, no token, no credits.

**GitHub:** https://github.com/akfamily/akshare
**Install:** `pip install akshare`
**Latest:** Actively maintained (16k+ GitHub stars, 2.9k forks)

**What it covers**
- China A-shares: SSE (Shanghai) and SZSE (Shenzhen) listed stocks
- Real-time quotes and key statistics for Chinese equities
- Historical OHLCV with forward/backward dividend and split adjustment
- Financial statements from CSRC (China Securities Regulatory Commission) filings
- Chinese macroeconomic indicators: GDP, CPI, PPI, M2, PMI, retail sales, trade balance
- Market indexes: CSI 300, CSI 500, SSE Composite, ChiNext, STAR Market
- Sector-level P/E ratios from Shanghai and Shenzhen exchanges
- Fund data, bond yields, futures, options (Chinese markets)
- Alternative data: money flows, institutional holdings, short interest

**Tools in this MCP that use AKShare**
| Tool | What it pulls |
|---|---|
| `ak_a_share_quote` | Live quote and stats for any A-share stock |
| `ak_a_share_history` | Historical daily prices with adjustment |
| `ak_a_share_financials` | Income statement and balance sheet from CSRC filings |
| `ak_macro_china` | GDP, CPI, PPI, M2, PMI, retail sales, industrial output, trade |
| `ak_index_quote` | CSI 300, CSI 500, SSE, SZSE, ChiNext, STAR levels |
| `ak_sector_pe` | Current P/E by sector for Shanghai or Shenzhen exchange |

**Limitations**
- ⚠️ **China-focused** — limited global/US stock coverage. Use yfinance for non-Chinese stocks.
- ⚠️ **Scraping-based** — pulls from public Chinese financial portals. Occasional
  instability if source sites restructure (less common than yfinance breakages).
- ⚠️ **Research use** — data is intended for academic/research purposes per AKShare's license.
- ⚠️ **Language** — some raw data fields are returned in Chinese (Simplified).
  This server translates key fields to English where possible.
- ⚠️ **Verification** — for precise institutional-grade work, verify against
  Wind (万得), Bloomberg, or official CSRC filings.

**When to use it**
- Chinese A-share company research
- Chinese macro context for investment thesis or competitive analysis
- Sector benchmarking within Chinese markets
- Companies dual-listed in China and Hong Kong/US

---

## Using Both Together

The two libraries complement each other cleanly:

```
Global stocks (US, EU, HK)      →  yfinance
China A-shares                  →  AKShare
Chinese macro indicators         →  AKShare
Analyst estimates (global)      →  yfinance
Sector P/E (China markets)      →  AKShare
Multi-market comps table        →  Both (combine outputs)
```

**Example workflow — cross-border comps table:**
1. `yf_peers_comps` → pull US/HK peers
2. `ak_a_share_quote` → pull Chinese A-share peers
3. Combine into `comps_table` tool for unified analysis

---

## Installation

```bash
pip install yfinance akshare mcp
```

## Disclaimer

Data from yfinance and AKShare is for research and analytical purposes only.
Neither library is affiliated with or endorsed by their underlying data sources
(Yahoo Finance and Chinese financial portals respectively).
Always verify figures against audited financials, official exchange data,
or institutional-grade data providers (Bloomberg, Wind, FactSet, Capital IQ)
before use in client-facing materials, investment decisions, or regulatory filings.
