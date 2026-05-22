#!/usr/bin/env python3
"""
Finance MCP — Market Data Server
Provides live financial data via yfinance (global) and AKShare (China).

Data Sources
------------
yfinance  : Unofficial Yahoo Finance wrapper. Free, no API key. Covers global
            equities, financials, analyst estimates, options. Reliable for
            light/moderate use; heavy use may trigger Yahoo rate-limits.
            Not affiliated with or endorsed by Yahoo Inc.
            For personal/research use only per Yahoo's Terms of Service.

AKShare   : Open-source Chinese financial data library. Free, no API key.
            Pulls from Eastmoney, Sina Finance, and other authoritative
            Chinese financial portals. Best-in-class for A-share data,
            macro indicators, and China market intelligence.
            Data is for academic/research purposes per AKShare's license.
"""

import json
import sys
import asyncio
from datetime import datetime, date

# ── dependency check ──────────────────────────────────────────────────────────
missing = []
try:
    import yfinance as yf
except ImportError:
    missing.append("yfinance")

try:
    import akshare as ak
except ImportError:
    missing.append("akshare")

if missing:
    print(
        f"ERROR: Missing packages: {', '.join(missing)}\n"
        f"Run:  pip install {' '.join(missing)}\n"
        f"Then restart Claude Desktop.",
        file=sys.stderr,
    )
    sys.exit(1)

# ── MCP SDK ───────────────────────────────────────────────────────────────────
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print(
        "ERROR: mcp package not found.\nRun: pip install mcp",
        file=sys.stderr,
    )
    sys.exit(1)

server = Server("finance-market-data")

# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def today():
    return date.today().isoformat()

def fmt_num(val, decimals=2, prefix="", suffix="", na="N/A"):
    """Safely format a numeric value."""
    try:
        if val is None or (isinstance(val, float) and (val != val)):  # NaN check
            return na
        return f"{prefix}{val:,.{decimals}f}{suffix}"
    except Exception:
        return na

def fmt_pct(val, na="N/A"):
    try:
        if val is None:
            return na
        return f"{val * 100:.2f}%"
    except Exception:
        return na

def safe(d, *keys, default="N/A"):
    """Safely traverse nested dict."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d if d not in (None, "", "None") else default

def df_to_md(df, max_rows=10):
    """Convert a pandas DataFrame to a markdown table."""
    if df is None or df.empty:
        return "_No data returned._"
    df = df.head(max_rows).reset_index()
    df.columns = [str(c) for c in df.columns]
    header = "| " + " | ".join(df.columns) + " |"
    sep    = "|" + "|".join(["---"] * len(df.columns)) + "|"
    rows   = []
    for _, row in df.iterrows():
        cells = []
        for v in row:
            try:
                if isinstance(v, float):
                    cells.append(f"{v:,.2f}")
                else:
                    cells.append(str(v)[:40])
            except Exception:
                cells.append("—")
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)

# ═════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRY
# ═════════════════════════════════════════════════════════════════════════════

TOOLS = [

    # ── DATA SOURCE NOTES ─────────────────────────────────────────────────────
    Tool(
        name="data_sources",
        description=(
            "Explain the two data sources powering this server — yfinance and AKShare — "
            "including what they cover, their limitations, and when to use each."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # yfinance TOOLS  (global markets — US, EU, HK, etc.)
    # ══════════════════════════════════════════════════════════════════════════

    Tool(
        name="yf_quote",
        description=(
            "[yfinance] Get a real-time quote and key statistics for any global ticker. "
            "Returns price, market cap, EV, P/E, EV/EBITDA, revenue, EBITDA, margins, "
            "52-week range, analyst target, and beta. "
            "Use to auto-populate comps tables, one-pagers, or DCF inputs."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Yahoo Finance ticker symbol (e.g. AAPL, MSFT, 0700.HK, ASML.AS)"
                }
            },
            "required": ["ticker"],
        },
    ),

    Tool(
        name="yf_financials",
        description=(
            "[yfinance] Pull annual or quarterly financial statements for a global ticker. "
            "Returns income statement, balance sheet, and cash flow statement. "
            "Use to populate DCF models, LBO inputs, or earnings analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticker":  {"type": "string", "description": "Yahoo Finance ticker (e.g. AAPL)"},
                "period":  {
                    "type": "string",
                    "enum": ["annual", "quarterly"],
                    "description": "annual or quarterly",
                    "default": "annual"
                },
                "statement": {
                    "type": "string",
                    "enum": ["income", "balance_sheet", "cashflow"],
                    "description": "Which statement to return",
                    "default": "income"
                }
            },
            "required": ["ticker"],
        },
    ),

    Tool(
        name="yf_price_history",
        description=(
            "[yfinance] Download historical OHLCV price data for any global ticker. "
            "Returns daily open, high, low, close, volume. "
            "Use for charting, return analysis, or volatility calculation."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticker":     {"type": "string", "description": "Yahoo Finance ticker"},
                "period":     {
                    "type": "string",
                    "enum": ["1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"],
                    "description": "Data period",
                    "default": "1y"
                },
                "interval":   {
                    "type": "string",
                    "enum": ["1d", "1wk", "1mo"],
                    "description": "Data frequency",
                    "default": "1d"
                }
            },
            "required": ["ticker"],
        },
    ),

    Tool(
        name="yf_peers_comps",
        description=(
            "[yfinance] Pull key valuation multiples for a list of tickers simultaneously. "
            "Returns a ready-to-use comps table with EV/EBITDA, EV/Revenue, P/E, P/B, "
            "EBITDA margin, and revenue growth for each ticker. "
            "Use to auto-build the comps_table tool inputs."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of Yahoo Finance tickers (e.g. ['CRM', 'NOW', 'WDAY'])"
                }
            },
            "required": ["tickers"],
        },
    ),

    Tool(
        name="yf_analyst_estimates",
        description=(
            "[yfinance] Get analyst consensus estimates and price targets for a ticker. "
            "Returns EPS estimates, revenue estimates, recommendation trend, "
            "and analyst price target (mean, low, high). "
            "Use to populate earnings_snapshot estimates or validate DCF assumptions."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Yahoo Finance ticker"}
            },
            "required": ["ticker"],
        },
    ),

    Tool(
        name="yf_earnings_calendar",
        description=(
            "[yfinance] Get upcoming earnings date and recent earnings history for a ticker. "
            "Returns next earnings date, EPS actual vs estimate for recent quarters. "
            "Use to time earnings_snapshot analysis or flag upcoming catalysts."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Yahoo Finance ticker"}
            },
            "required": ["ticker"],
        },
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # AKShare TOOLS  (China markets — A-shares, macro, funds)
    # ══════════════════════════════════════════════════════════════════════════

    Tool(
        name="ak_a_share_quote",
        description=(
            "[AKShare] Get real-time quote and key stats for a China A-share stock. "
            "Returns price, market cap, P/E, P/B, turnover rate, and sector. "
            "Use for Chinese equity research, comps, or one-pagers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "A-share stock code without exchange suffix (e.g. '000001' for Ping An, '600519' for Moutai)"
                }
            },
            "required": ["symbol"],
        },
    ),

    Tool(
        name="ak_a_share_history",
        description=(
            "[AKShare] Download historical daily price data for a China A-share stock. "
            "Returns OHLCV data with optional adjustment for dividends/splits. "
            "Use for return analysis, charting, or volatility calculation."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol":     {"type": "string", "description": "A-share stock code (e.g. '000001')"},
                "start_date": {"type": "string", "description": "Start date YYYYMMDD (e.g. '20230101')"},
                "end_date":   {"type": "string", "description": "End date YYYYMMDD (e.g. '20241231')"},
                "adjust":     {
                    "type": "string",
                    "enum": ["", "qfq", "hfq"],
                    "description": "Price adjustment: '' = none, 'qfq' = forward-adjusted, 'hfq' = backward-adjusted",
                    "default": "qfq"
                }
            },
            "required": ["symbol"],
        },
    ),

    Tool(
        name="ak_a_share_financials",
        description=(
            "[AKShare] Pull financial statement data for a China A-share company. "
            "Returns key income statement and balance sheet metrics from CSRC filings. "
            "Use for Chinese company DCF inputs, comps, or fundamental analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "A-share stock code (e.g. '600519')"
                }
            },
            "required": ["symbol"],
        },
    ),

    Tool(
        name="ak_macro_china",
        description=(
            "[AKShare] Fetch Chinese macroeconomic indicators. "
            "Covers GDP growth, CPI, PPI, M2 money supply, PMI, retail sales, "
            "industrial output, and trade balance. "
            "Use for macro context in competitive analysis or investment thesis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "enum": ["gdp", "cpi", "ppi", "m2", "pmi_manufacturing", "pmi_services", "retail_sales", "industrial_output", "trade_balance"],
                    "description": "Macro indicator to fetch"
                }
            },
            "required": ["indicator"],
        },
    ),

    Tool(
        name="ak_index_quote",
        description=(
            "[AKShare] Get current levels and performance for major Chinese market indexes. "
            "Covers CSI 300, CSI 500, SSE Composite, SZSE Component, ChiNext, STAR Market. "
            "Use for market context, benchmark comparison, or competitive analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "enum": ["csi300", "csi500", "sse_composite", "szse_component", "chinext", "star"],
                    "description": "Chinese market index"
                }
            },
            "required": ["index"],
        },
    ),

    Tool(
        name="ak_sector_pe",
        description=(
            "[AKShare] Get current P/E ratios by sector for the China A-share market. "
            "Returns sector-level valuation multiples from Shanghai and Shenzhen exchanges. "
            "Use for sector benchmarking, comps context, or relative value analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "exchange": {
                    "type": "string",
                    "enum": ["shanghai", "shenzhen"],
                    "description": "Exchange to pull sector P/E from",
                    "default": "shanghai"
                }
            },
            "required": [],
        },
    ),
]

# ═════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ═════════════════════════════════════════════════════════════════════════════

# ── data_sources ──────────────────────────────────────────────────────────────
def handle_data_sources(_):
    return """## Market Data Sources — Finance MCP

---

### 📊 yfinance
**What it is:** An open-source Python library that downloads data from Yahoo Finance's
public APIs. The most widely used free financial data tool in the Python ecosystem.

**What it covers:**
- Global equities: US (NYSE, NASDAQ), Europe, Hong Kong, Japan, and more
- Real-time quotes, OHLCV price history (daily, weekly, monthly)
- Financial statements: income statement, balance sheet, cash flow (annual & quarterly)
- Valuation multiples: P/E, EV/EBITDA, EV/Revenue, P/B, P/S
- Analyst consensus: EPS estimates, revenue estimates, price targets, recommendations
- Earnings calendar: upcoming dates, historical actuals vs. estimates
- Options chains, dividends, stock splits

**Limitations:**
- ⚠️ **Unofficial** — not affiliated with or endorsed by Yahoo Inc.
- ⚠️ **Rate limits** — heavy use (many calls in quick succession) may trigger Yahoo's
  rate-limiting. Works well for light/moderate MCP use (5–20 calls per session).
- ⚠️ **Fragility** — Yahoo occasionally changes their internal API, which can break
  yfinance temporarily until maintainers push a fix (usually within days).
- ⚠️ **Terms of service** — data is for personal/research use only per Yahoo's ToS.
  Not for commercial redistribution.
- ⚠️ **China A-shares** — limited coverage; use AKShare for Chinese domestic stocks.

**Best for:** Global equity research, US/EU company analysis, populating DCF/comps inputs,
analyst estimate feeds, earnings analysis.

**No API key required.** Install with: `pip install yfinance`

---

### 🇨🇳 AKShare
**What it is:** An open-source Python financial data library built specifically for
Chinese financial markets. Sources data from Eastmoney (东方财富), Sina Finance (新浪财经),
and other authoritative Chinese financial portals. Completely free, no registration needed.

**What it covers:**
- China A-shares: SSE (Shanghai) and SZSE (Shenzhen) listed stocks
- Real-time quotes, historical OHLCV with dividend/split adjustment
- Financial statements from CSRC (China Securities Regulatory Commission) filings
- Chinese macroeconomic indicators: GDP, CPI, PPI, M2, PMI, trade balance
- Market indexes: CSI 300, CSI 500, SSE Composite, ChiNext, STAR Market
- Sector-level P/E ratios from Shanghai and Shenzhen exchanges
- Fund data, bond yields, futures, options (Chinese markets)

**Limitations:**
- ⚠️ **China-focused** — limited global/US stock coverage; use yfinance for non-Chinese stocks.
- ⚠️ **Scraping-based** — pulls from public web portals; occasional instability if source
  sites change their structure.
- ⚠️ **Research use** — data is intended for academic/research purposes per AKShare's license.
- ⚠️ **Language** — some raw data fields are returned in Chinese; this server translates
  key fields to English where possible.

**Best for:** China A-share equity research, Chinese macro analysis, sector benchmarking
in Chinese markets, competitive analysis involving Chinese-listed companies.

**No API key required.** Install with: `pip install akshare`

---

### When to Use Which

| Need | Use |
|---|---|
| US/EU stock quote or financials | yfinance |
| Analyst estimates and price targets | yfinance |
| Earnings calendar and history | yfinance |
| Multi-ticker comps table (global) | yfinance |
| China A-share quote or financials | AKShare |
| Chinese macro indicators | AKShare |
| China market sector P/E | AKShare |
| CSI 300 / SSE index levels | AKShare |
| Both Chinese and global peers | Both together |

---

### Installation
```bash
pip install yfinance akshare mcp
```
"""

# ── yf_quote ──────────────────────────────────────────────────────────────────
def handle_yf_quote(args):
    ticker = args["ticker"].upper()
    try:
        t    = yf.Ticker(ticker)
        info = t.info
    except Exception as e:
        return f"❌ Could not fetch data for {ticker}: {e}"

    name    = safe(info, "longName", default=ticker)
    sector  = safe(info, "sector")
    industry= safe(info, "industry")
    exchange= safe(info, "exchange")
    currency= safe(info, "currency", default="USD")

    price   = safe(info, "currentPrice") or safe(info, "regularMarketPrice")
    prev_cl = safe(info, "previousClose")
    change  = None
    if isinstance(price, (int, float)) and isinstance(prev_cl, (int, float)):
        change = (price - prev_cl) / prev_cl

    mktcap  = info.get("marketCap")
    ev      = info.get("enterpriseValue")
    pe      = info.get("trailingPE")
    fpe     = info.get("forwardPE")
    ev_rev  = info.get("enterpriseToRevenue")
    ev_ebitda = info.get("enterpriseToEbitda")
    pb      = info.get("priceToBook")
    rev     = info.get("totalRevenue")
    ebitda  = info.get("ebitda")
    gm      = info.get("grossMargins")
    om      = info.get("operatingMargins")
    pm      = info.get("profitMargins")
    beta    = info.get("beta")
    w52h    = info.get("fiftyTwoWeekHigh")
    w52l    = info.get("fiftyTwoWeekLow")
    tgt     = info.get("targetMeanPrice")
    rec     = safe(info, "recommendationKey")
    div_yld = info.get("dividendYield")

    def m(v, b=1e6):
        if v is None: return "N/A"
        if v >= 1e12: return f"${v/1e12:.2f}T"
        if v >= 1e9:  return f"${v/1e9:.2f}B"
        return f"${v/1e6:.0f}M"

    lines = [
        f"## {name} ({ticker})",
        f"*{exchange} · {sector} · {industry} · {today()}*\n",
        "### Price & Market Data",
        "| | |", "|---|---|",
        f"| Price ({currency}) | {fmt_num(price, prefix='$')} |",
        f"| Day Change | {fmt_pct(change)} |" if change else "",
        f"| 52-Week Range | {fmt_num(w52l, prefix='$')} – {fmt_num(w52h, prefix='$')} |",
        f"| Market Cap | {m(mktcap)} |",
        f"| Enterprise Value | {m(ev)} |",
        f"| Beta | {fmt_num(beta)} |",
        "",
        "### Valuation Multiples",
        "| Multiple | Value |", "|---|---|",
        f"| P/E (Trailing) | {fmt_num(pe)}x |",
        f"| P/E (Forward) | {fmt_num(fpe)}x |",
        f"| EV/Revenue | {fmt_num(ev_rev)}x |",
        f"| EV/EBITDA | {fmt_num(ev_ebitda)}x |",
        f"| P/B | {fmt_num(pb)}x |",
        "",
        "### Financials (TTM)",
        "| | |", "|---|---|",
        f"| Revenue | {m(rev)} |",
        f"| EBITDA | {m(ebitda)} |",
        f"| Gross Margin | {fmt_pct(gm)} |",
        f"| Operating Margin | {fmt_pct(om)} |",
        f"| Net Margin | {fmt_pct(pm)} |",
        "",
        "### Analyst Coverage",
        "| | |", "|---|---|",
        f"| Recommendation | {rec.upper() if isinstance(rec, str) else 'N/A'} |",
        f"| Mean Price Target | {fmt_num(tgt, prefix='$')} |",
        f"| Upside to Target | {fmt_pct((tgt/price - 1) if isinstance(tgt,(int,float)) and isinstance(price,(int,float)) and price else None)} |",
        f"| Dividend Yield | {fmt_pct(div_yld)} |",
        "",
        f"> *Source: yfinance / Yahoo Finance · {today()}*",
        "> ⚠️ Data is unofficial. Verify against Bloomberg/FactSet before use in client materials.",
    ]
    return "\n".join(l for l in lines if l != "")


# ── yf_financials ─────────────────────────────────────────────────────────────
def handle_yf_financials(args):
    ticker    = args["ticker"].upper()
    period    = args.get("period", "annual")
    statement = args.get("statement", "income")
    try:
        t = yf.Ticker(ticker)
        if period == "annual":
            if statement == "income":        df = t.financials
            elif statement == "balance_sheet": df = t.balance_sheet
            else:                             df = t.cashflow
        else:
            if statement == "income":        df = t.quarterly_financials
            elif statement == "balance_sheet": df = t.quarterly_balance_sheet
            else:                             df = t.quarterly_cashflow
    except Exception as e:
        return f"❌ Could not fetch financials for {ticker}: {e}"

    if df is None or df.empty:
        return f"❌ No {statement} data found for {ticker}."

    # Transpose so dates are rows
    df = df.T
    df.index = [str(i)[:10] for i in df.index]

    label_map = {
        "income": "Income Statement",
        "balance_sheet": "Balance Sheet",
        "cashflow": "Cash Flow Statement"
    }

    lines = [
        f"## {ticker} — {label_map[statement]} ({period.capitalize()})",
        f"*Source: yfinance · {today()}*\n",
        df_to_md(df.reset_index().rename(columns={"index": "Period"}), max_rows=8),
        "",
        "> All figures in USD. N/A = not reported or not applicable.",
        "> ⚠️ Verify against SEC filings or audited financials before use in client materials.",
    ]
    return "\n".join(lines)


# ── yf_price_history ──────────────────────────────────────────────────────────
def handle_yf_price_history(args):
    ticker   = args["ticker"].upper()
    period   = args.get("period", "1y")
    interval = args.get("interval", "1d")
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
    except Exception as e:
        return f"❌ Could not fetch price history for {ticker}: {e}"

    if df is None or df.empty:
        return f"❌ No price data returned for {ticker}."

    # Summary stats
    close = df["Close"]
    start_price = float(close.iloc[0])
    end_price   = float(close.iloc[-1])
    total_ret   = (end_price / start_price - 1)
    high        = float(df["High"].max())
    low         = float(df["Low"].min())
    avg_vol     = float(df["Volume"].mean())

    lines = [
        f"## {ticker} — Price History ({period}, {interval})",
        f"*Source: yfinance · {today()}*\n",
        "### Summary Statistics",
        "| | |", "|---|---|",
        f"| Start Price | ${start_price:,.2f} |",
        f"| End Price | ${end_price:,.2f} |",
        f"| Total Return | {total_ret*100:+.1f}% |",
        f"| Period High | ${high:,.2f} |",
        f"| Period Low | ${low:,.2f} |",
        f"| Avg Daily Volume | {avg_vol:,.0f} |",
        f"| Data Points | {len(df):,} |",
        "",
        "### Recent Data (last 10 sessions)",
        df_to_md(df.tail(10).reset_index(), max_rows=10),
        "",
        "> ⚠️ Unofficial data source. Verify against exchange feeds for precision work.",
    ]
    return "\n".join(lines)


# ── yf_peers_comps ────────────────────────────────────────────────────────────
def handle_yf_peers_comps(args):
    tickers = [t.upper() for t in args["tickers"]]
    rows    = []

    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            rows.append({
                "Ticker":        ticker,
                "Name":          (info.get("shortName") or ticker)[:25],
                "EV/EBITDA":     fmt_num(info.get("enterpriseToEbitda")) + "x",
                "EV/Revenue":    fmt_num(info.get("enterpriseToRevenue")) + "x",
                "P/E (Fwd)":     fmt_num(info.get("forwardPE")) + "x",
                "P/B":           fmt_num(info.get("priceToBook")) + "x",
                "EBITDA Mgn":    fmt_pct(info.get("ebitdaMargins")),
                "Rev Growth":    fmt_pct(info.get("revenueGrowth")),
                "Mkt Cap":       f"${info['marketCap']/1e9:.1f}B" if info.get("marketCap") else "N/A",
            })
        except Exception as e:
            rows.append({"Ticker": ticker, "Name": f"Error: {e}"})

    if not rows:
        return "❌ No data returned."

    keys   = ["Ticker", "Name", "EV/EBITDA", "EV/Revenue", "P/E (Fwd)", "P/B", "EBITDA Mgn", "Rev Growth", "Mkt Cap"]
    header = "| " + " | ".join(keys) + " |"
    sep    = "|" + "|".join(["---"] * len(keys)) + "|"
    body   = [
        "| " + " | ".join(str(r.get(k, "N/A")) for k in keys) + " |"
        for r in rows
    ]

    lines = [
        f"## Peer Comps — {', '.join(tickers)}",
        f"*Source: yfinance · {today()}*\n",
        header, sep, *body,
        "",
        "> Copy these multiples directly into the `comps_table` tool for benchmarking analysis.",
        "> ⚠️ Verify against live Bloomberg/FactSet data before use in client materials.",
    ]
    return "\n".join(lines)


# ── yf_analyst_estimates ──────────────────────────────────────────────────────
def handle_yf_analyst_estimates(args):
    ticker = args["ticker"].upper()
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        eps  = t.earnings_estimate if hasattr(t, "earnings_estimate") else None
    except Exception as e:
        return f"❌ Could not fetch estimates for {ticker}: {e}"

    tgt_mean = info.get("targetMeanPrice")
    tgt_low  = info.get("targetLowPrice")
    tgt_high = info.get("targetHighPrice")
    price    = info.get("currentPrice") or info.get("regularMarketPrice")
    rec      = safe(info, "recommendationKey", default="N/A")
    num_anal = info.get("numberOfAnalystOpinions", "N/A")

    upside = None
    if isinstance(tgt_mean, (int,float)) and isinstance(price, (int,float)) and price:
        upside = (tgt_mean / price - 1)

    lines = [
        f"## {ticker} — Analyst Estimates & Targets",
        f"*Source: yfinance · {today()}*\n",
        "### Price Targets",
        "| | |", "|---|---|",
        f"| Current Price | {fmt_num(price, prefix='$')} |",
        f"| Mean Target | {fmt_num(tgt_mean, prefix='$')} |",
        f"| Low Target | {fmt_num(tgt_low, prefix='$')} |",
        f"| High Target | {fmt_num(tgt_high, prefix='$')} |",
        f"| Implied Upside | {fmt_pct(upside)} |",
        f"| Consensus | {rec.upper() if isinstance(rec, str) else 'N/A'} |",
        f"| # Analysts | {num_anal} |",
        "",
        "### Forward Estimates",
        "| Metric | Current Year | Next Year |", "|---|---|---|",
        f"| EPS (Fwd) | {fmt_num(info.get('forwardEps'), prefix='$')} | N/A |",
        f"| P/E (Fwd) | {fmt_num(info.get('forwardPE'))}x | N/A |",
        f"| Revenue (TTM) | ${info['totalRevenue']/1e9:.2f}B | N/A |" if info.get("totalRevenue") else "",
        "",
        "> ⚠️ Consensus estimates are as of data pull date. Verify against Bloomberg/FactSet.",
    ]
    return "\n".join(l for l in lines if l != "")


# ── yf_earnings_calendar ──────────────────────────────────────────────────────
def handle_yf_earnings_calendar(args):
    ticker = args["ticker"].upper()
    try:
        t    = yf.Ticker(ticker)
        cal  = t.calendar
        info = t.info
    except Exception as e:
        return f"❌ Could not fetch earnings data for {ticker}: {e}"

    next_date = "N/A"
    if isinstance(cal, dict):
        nd = cal.get("Earnings Date")
        if nd:
            next_date = str(nd[0])[:10] if hasattr(nd, "__iter__") else str(nd)[:10]
    elif hasattr(cal, "iloc"):
        try:
            next_date = str(cal.iloc[0, 0])[:10]
        except Exception:
            pass

    lines = [
        f"## {ticker} — Earnings Calendar",
        f"*Source: yfinance · {today()}*\n",
        "### Upcoming Earnings",
        "| | |", "|---|---|",
        f"| Next Earnings Date | {next_date} |",
        f"| Fiscal Year End | {safe(info, 'lastFiscalYearEnd', default='N/A')[:10] if isinstance(safe(info, 'lastFiscalYearEnd'), str) else 'N/A'} |",
        "",
        "> Use this to time earnings_snapshot analysis and flag upcoming catalysts.",
        "> ⚠️ Dates are estimates and subject to change. Confirm via company IR website.",
    ]
    return "\n".join(l for l in lines if l != "")


# ── ak_a_share_quote ──────────────────────────────────────────────────────────
def handle_ak_a_share_quote(args):
    symbol = args["symbol"].strip()
    try:
        df = ak.stock_individual_info_em(symbol=symbol)
    except Exception as e:
        return f"❌ Could not fetch A-share data for {symbol}: {e}\n\nTip: Use 6-digit code without exchange suffix (e.g. '000001', '600519')."

    if df is None or df.empty:
        return f"❌ No data returned for symbol {symbol}."

    # AKShare returns a two-column DataFrame: item / value
    data = {}
    try:
        for _, row in df.iterrows():
            data[str(row.iloc[0])] = str(row.iloc[1])
    except Exception:
        pass

    lines = [
        f"## A-Share Quote — {symbol}",
        f"*Source: AKShare / Eastmoney · {today()}*\n",
        "| Field | Value |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in data.items()],
        "",
        "> Data sourced from Eastmoney (东方财富). For research purposes only.",
        "> ⚠️ Verify against Wind/Bloomberg for precision work.",
    ]
    return "\n".join(lines)


# ── ak_a_share_history ────────────────────────────────────────────────────────
def handle_ak_a_share_history(args):
    symbol     = args["symbol"].strip()
    start_date = args.get("start_date", "20230101")
    end_date   = args.get("end_date",   date.today().strftime("%Y%m%d"))
    adjust     = args.get("adjust", "qfq")

    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust
        )
    except Exception as e:
        return f"❌ Could not fetch price history for {symbol}: {e}"

    if df is None or df.empty:
        return f"❌ No price history returned for {symbol}."

    close_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
    try:
        start_p = float(df.iloc[0][close_col])
        end_p   = float(df.iloc[-1][close_col])
        ret     = (end_p / start_p - 1) * 100
    except Exception:
        start_p = end_p = ret = None

    lines = [
        f"## A-Share Price History — {symbol}",
        f"*{start_date[:4]}-{start_date[4:6]}-{start_date[6:]} to {end_date[:4]}-{end_date[4:6]}-{end_date[6:]} · Adjust: {adjust or 'none'}*",
        f"*Source: AKShare / Eastmoney · {today()}*\n",
    ]
    if ret is not None:
        lines += [
            "### Period Summary",
            "| | |", "|---|---|",
            f"| Start Price | ¥{start_p:,.2f} |",
            f"| End Price | ¥{end_p:,.2f} |",
            f"| Total Return | {ret:+.1f}% |",
            f"| Data Points | {len(df):,} |",
            "",
        ]
    lines += [
        "### Recent Data (last 10 sessions)",
        df_to_md(df.tail(10), max_rows=10),
        "",
        "> ⚠️ For research purposes only. Verify against official exchange data.",
    ]
    return "\n".join(lines)


# ── ak_a_share_financials ─────────────────────────────────────────────────────
def handle_ak_a_share_financials(args):
    symbol = args["symbol"].strip()
    try:
        df = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按年度")
    except Exception as e:
        return f"❌ Could not fetch financials for {symbol}: {e}"

    if df is None or df.empty:
        return f"❌ No financial data returned for {symbol}."

    lines = [
        f"## A-Share Financial Summary — {symbol}",
        f"*Source: AKShare / Tonghuashun · {today()}*\n",
        df_to_md(df, max_rows=8),
        "",
        "> Data sourced from CSRC filings via Tonghuashun. For research purposes only.",
        "> ⚠️ Verify against official CSRC/EDGAR filings before use in client materials.",
    ]
    return "\n".join(lines)


# ── ak_macro_china ────────────────────────────────────────────────────────────
def handle_ak_macro_china(args):
    indicator = args["indicator"]

    indicator_map = {
        "gdp":                ("macro_china_gdp", "China GDP Growth Rate"),
        "cpi":                ("macro_china_cpi_monthly", "China CPI (Monthly)"),
        "ppi":                ("macro_china_ppi_monthly", "China PPI (Monthly)"),
        "m2":                 ("macro_china_m2_yearly", "China M2 Money Supply"),
        "pmi_manufacturing":  ("macro_china_pmi_yearly", "China Manufacturing PMI"),
        "pmi_services":       ("macro_china_non_man_pmi", "China Non-Manufacturing PMI"),
        "retail_sales":       ("macro_china_retail_total", "China Retail Sales"),
        "industrial_output":  ("macro_china_industrial_production_yoy", "China Industrial Output YoY"),
        "trade_balance":      ("macro_china_trade_balance", "China Trade Balance"),
    }

    if indicator not in indicator_map:
        return f"❌ Unknown indicator: {indicator}. Choose from: {', '.join(indicator_map.keys())}"

    func_name, label = indicator_map[indicator]
    try:
        func = getattr(ak, func_name)
        df   = func()
    except AttributeError:
        return f"❌ AKShare function `{func_name}` not found. The AKShare API may have changed — try `pip install akshare --upgrade`."
    except Exception as e:
        return f"❌ Could not fetch {label}: {e}"

    if df is None or df.empty:
        return f"❌ No data returned for {label}."

    lines = [
        f"## {label}",
        f"*Source: AKShare · {today()}*\n",
        df_to_md(df.tail(12), max_rows=12),
        "",
        "> Source: National Bureau of Statistics of China (NBS) via AKShare.",
        "> For research and context purposes only.",
    ]
    return "\n".join(lines)


# ── ak_index_quote ────────────────────────────────────────────────────────────
def handle_ak_index_quote(args):
    index = args["index"]

    index_map = {
        "csi300":        ("000300", "CSI 300"),
        "csi500":        ("000905", "CSI 500"),
        "sse_composite": ("000001", "SSE Composite"),
        "szse_component":("399001", "SZSE Component"),
        "chinext":       ("399006", "ChiNext"),
        "star":          ("000688", "STAR Market 50"),
    }

    if index not in index_map:
        return f"❌ Unknown index: {index}"

    code, label = index_map[index]
    try:
        df = ak.stock_zh_index_daily(symbol=f"sh{code}" if code.startswith("0") else f"sz{code}")
    except Exception as e:
        return f"❌ Could not fetch index data for {label}: {e}"

    if df is None or df.empty:
        return f"❌ No data returned for {label}."

    latest = df.iloc[-1]
    prev   = df.iloc[-2] if len(df) > 1 else None

    try:
        close  = float(latest.get("close", latest.iloc[-1]))
        p_close= float(prev.get("close", prev.iloc[-1])) if prev is not None else None
        chg    = (close/p_close - 1) if p_close else None
    except Exception:
        close = chg = None

    lines = [
        f"## {label} ({code})",
        f"*Source: AKShare · {today()}*\n",
        "| | |", "|---|---|",
        f"| Latest Close | {fmt_num(close, prefix='¥')} |",
        f"| Day Change | {fmt_pct(chg)} |" if chg is not None else "",
        "",
        "### Recent History (last 10 sessions)",
        df_to_md(df.tail(10), max_rows=10),
        "",
        "> Source: Shanghai/Shenzhen Stock Exchange via AKShare.",
    ]
    return "\n".join(l for l in lines if l != "")


# ── ak_sector_pe ─────────────────────────────────────────────────────────────
def handle_ak_sector_pe(args):
    exchange = args.get("exchange", "shanghai")
    label    = "Shanghai (SSE)" if exchange == "shanghai" else "Shenzhen (SZSE)"
    ex_code  = "sh" if exchange == "shanghai" else "sz"

    try:
        df = ak.stock_sector_pe_ratio_cninfo(date=date.today().strftime("%Y%m%d"), symbol=ex_code)
    except Exception as e:
        # fallback
        try:
            df = ak.stock_sector_pe_ratio_cninfo(
                date=(date.today().replace(day=1)).strftime("%Y%m%d"),
                symbol=ex_code
            )
        except Exception as e2:
            return f"❌ Could not fetch sector P/E for {label}: {e}\nFallback also failed: {e2}"

    if df is None or df.empty:
        return f"❌ No sector P/E data returned for {label}."

    lines = [
        f"## {label} — Sector P/E Ratios",
        f"*Source: AKShare / CNINFO · {today()}*\n",
        df_to_md(df, max_rows=30),
        "",
        "> Use for sector benchmarking and relative valuation in Chinese equity research.",
        "> Source: China Securities Information (巨潮资讯) via AKShare.",
    ]
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═════════════════════════════════════════════════════════════════════════════

DISPATCH = {
    "data_sources":             handle_data_sources,
    "yf_quote":                 handle_yf_quote,
    "yf_financials":            handle_yf_financials,
    "yf_price_history":         handle_yf_price_history,
    "yf_peers_comps":           handle_yf_peers_comps,
    "yf_analyst_estimates":     handle_yf_analyst_estimates,
    "yf_earnings_calendar":     handle_yf_earnings_calendar,
    "ak_a_share_quote":         handle_ak_a_share_quote,
    "ak_a_share_history":       handle_ak_a_share_history,
    "ak_a_share_financials":    handle_ak_a_share_financials,
    "ak_macro_china":           handle_ak_macro_china,
    "ak_index_quote":           handle_ak_index_quote,
    "ak_sector_pe":             handle_ak_sector_pe,
}

@server.list_tools()
async def list_tools():
    return TOOLS

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    handler = DISPATCH.get(name)
    if not handler:
        return [TextContent(type="text", text=f"❌ Unknown tool: {name}")]
    try:
        result = handler(arguments or {})
        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ Error in {name}: {e}")]

# ═════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
