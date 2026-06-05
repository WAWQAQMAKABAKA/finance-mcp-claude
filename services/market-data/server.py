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

Tonghuashun (THS) scraper:
            HTTP scraper targeting 10jqka.com.cn. Used because AKShare's
            Eastmoney-based quote/history endpoints are blocked by the MCP
            proxy (push2.eastmoney.com → ProxyError). THS endpoints are not
            blocked. Returns fundamentals, analyst ratings, block trades,
            and margin data — NOT a live intraday price stream.
"""

import json
import os
import re
import sys
import asyncio
import urllib.request
from datetime import date

# ── dependency check ──────────────────────────────────────────────────────────
REQUIRED_PACKAGES = ["yfinance", "akshare"]
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
    print("ERROR: mcp package not found.\nRun: pip install mcp", file=sys.stderr)
    sys.exit(1)

# ── shared formatting utils ───────────────────────────────────────────────────
_utils_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "utils")
sys.path.insert(0, os.path.abspath(_utils_path))
from formatting import today, fmt_num, fmt_pct, fmt_cny, fmt_usd, safe, df_to_md, build_kv_table, source_footer

server = Server("finance-market-data")

# ── THS scraper helper ────────────────────────────────────────────────────────
_THS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.10jqka.com.cn/",
}

def fetch_ths_page(symbol: str, path: str = "/") -> str:
    """
    Fetch a Tonghuashun stock page and return raw HTML.
    Raises on network error so callers can handle gracefully.

    URL pattern: https://stockpage.10jqka.com.cn/{symbol}{path}
    """
    url = f"https://stockpage.10jqka.com.cn/{symbol}{path}"
    req = urllib.request.Request(url, headers=_THS_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8", errors="replace")

# ═════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRY
# ═════════════════════════════════════════════════════════════════════════════

TOOLS = [

    Tool(
        name="data_sources",
        description=(
            "Explain the data sources powering this server — yfinance, AKShare, and the "
            "Tonghuashun scraper — including what each covers, its limitations, and when to use it."
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
            "Use for US, EU, and HK-listed stocks. "
            "⚠️ Subject to Yahoo rate limits — if this fails, fall back to web_search for the price."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Yahoo Finance ticker (e.g. AAPL, MSFT, 0700.HK, ASML.AS)"
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
                "ticker":    {"type": "string", "description": "Yahoo Finance ticker (e.g. AAPL)"},
                "period":    {"type": "string", "enum": ["annual", "quarterly"], "default": "annual"},
                "statement": {"type": "string", "enum": ["income", "balance_sheet", "cashflow"], "default": "income"},
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
                "ticker":   {"type": "string", "description": "Yahoo Finance ticker"},
                "period":   {"type": "string", "enum": ["1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"], "default": "1y"},
                "interval": {"type": "string", "enum": ["1d","1wk","1mo"], "default": "1d"},
            },
            "required": ["ticker"],
        },
    ),

    Tool(
        name="yf_peers_comps",
        description=(
            "[yfinance] Pull key valuation multiples for a list of tickers simultaneously. "
            "Returns EV/EBITDA, EV/Revenue, P/E, P/B, EBITDA margin, and revenue growth. "
            "Use to auto-build comps_table inputs. "
            "⚠️ Does not normalise currencies — do not mix CNY and USD tickers without noting the discrepancy."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "tickers": {"type": "array", "items": {"type": "string"}, "description": "List of Yahoo Finance tickers"}
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
            "Returns next earnings date and EPS actuals vs estimates for recent quarters."
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
    # AKShare TOOLS  (China markets — macro, indexes, sector PE)
    # Note: ak_a_share_quote and ak_a_share_history are DISABLED.
    # Both hit push2.eastmoney.com / push2his.eastmoney.com which are blocked
    # by the MCP proxy (ProxyError — RemoteDisconnected). Use ak_a_share_quote_ths
    # for fundamentals and web_search for live price instead.
    # ══════════════════════════════════════════════════════════════════════════

    Tool(
        name="ak_a_share_financials",
        description=(
            "[AKShare] Pull multi-year financial statement data for a China A-share company "
            "from CSRC filings via Tonghuashun. "
            "Returns revenue, net profit, EPS, ROE, debt ratios across annual periods. "
            "Use for trend analysis, DCF inputs, or value investing fundamentals. "
            "Always call this alongside ak_a_share_quote_ths at the start of any A-share analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "6-digit A-share code (e.g. '600519')"}
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
            "Use for macro context in investment thesis or competitive analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "indicator": {
                    "type": "string",
                    "enum": ["gdp","cpi","ppi","m2","pmi_manufacturing","pmi_services","retail_sales","industrial_output","trade_balance"],
                    "description": "Macro indicator to fetch"
                }
            },
            "required": ["indicator"],
        },
    ),

    Tool(
        name="ak_index_quote",
        description=(
            "[AKShare] Get current levels and recent history for major Chinese market indexes. "
            "Covers CSI 300, CSI 500, SSE Composite, SZSE Component, ChiNext, STAR Market. "
            "Use for market context and benchmark comparison. "
            "✅ This tool works — it uses a different endpoint from the blocked Eastmoney quote tools."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "enum": ["csi300","csi500","sse_composite","szse_component","chinext","star"],
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
            "Use for sector benchmarking and relative value analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "exchange": {
                    "type": "string",
                    "enum": ["shanghai","shenzhen"],
                    "default": "shanghai",
                    "description": "Exchange to pull sector P/E from"
                }
            },
            "required": [],
        },
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # TONGHUASHUN SCRAPER  (A-share fundamentals via 10jqka.com.cn)
    # ══════════════════════════════════════════════════════════════════════════

    Tool(
        name="ak_a_share_quote_ths",
        description=(
            "[同花顺/Tonghuashun] Fetch A-share fundamentals and analyst data by scraping "
            "Tonghuashun (10jqka.com.cn). "
            "Returns: EPS, NAV/share, net profit, revenue, profit growth rate, share counts, "
            "CFO/share, analyst consensus (last 60 trading days), recent block trades, "
            "and margin balance data. "
            "Does NOT return a live intraday price — the page renders price via JavaScript "
            "which is not captured in the static HTML fetch. "
            "For live price: use web_search('股票代码 股价 今日'). "
            "Covers SSE (6xxxxx), SZSE (0xxxxx / 3xxxxx), and STAR Market (688xxx). "
            "✅ This tool works — 10jqka.com.cn is not blocked by the MCP proxy."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "6-digit A-share code without exchange suffix (e.g. '600519', '688012')"
                }
            },
            "required": ["symbol"],
        },
    ),

]

# ═════════════════════════════════════════════════════════════════════════════
# DISABLED TOOL STUBS
# These handlers are intentionally not registered in TOOLS or DISPATCH.
# They are kept here for reference and to make re-enabling straightforward.
#
# ak_a_share_quote   — blocked: push2.eastmoney.com → ProxyError
# ak_a_share_history — blocked: push2his.eastmoney.com → ProxyError
# ═════════════════════════════════════════════════════════════════════════════

# def handle_ak_a_share_quote(args):
#     """
#     DISABLED — hits push2.eastmoney.com which is blocked by the MCP proxy.
#     Error: HTTPSConnectionPool(host='push2.eastmoney.com', port=443):
#            Max retries exceeded (Caused by ProxyError → RemoteDisconnected)
#     To re-enable: uncomment handler, add Tool() to TOOLS, add to DISPATCH.
#     Replacement: use ak_a_share_quote_ths + web_search for live price.
#     """
#     symbol = args["symbol"].strip()
#     try:
#         df = ak.stock_individual_info_em(symbol=symbol)
#     except Exception as e:
#         return f"❌ Could not fetch A-share data for {symbol}: {e}"
#     if df is None or df.empty:
#         return f"❌ No data returned for symbol {symbol}."
#     data = {}
#     try:
#         for _, row in df.iterrows():
#             data[str(row.iloc[0])] = str(row.iloc[1])
#     except Exception:
#         pass
#     lines = [
#         f"## A-Share Quote — {symbol}",
#         f"*Source: AKShare / Eastmoney · {today()}*\n",
#         build_kv_table(data),
#         "",
#         source_footer("AKShare / Eastmoney (东方财富)", "Wind/Bloomberg"),
#     ]
#     return "\n".join(lines)


# def handle_ak_a_share_history(args):
#     """
#     DISABLED — hits push2his.eastmoney.com which is blocked by the MCP proxy.
#     Error: HTTPSConnectionPool(host='push2his.eastmoney.com', port=443):
#            Max retries exceeded (Caused by ProxyError → RemoteDisconnected)
#     To re-enable: uncomment handler, add Tool() to TOOLS, add to DISPATCH.
#     """
#     symbol     = args["symbol"].strip()
#     start_date = args.get("start_date", "20230101")
#     end_date   = args.get("end_date", date.today().strftime("%Y%m%d"))
#     adjust     = args.get("adjust", "qfq")
#     try:
#         df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
#                                 start_date=start_date, end_date=end_date, adjust=adjust)
#     except Exception as e:
#         return f"❌ Could not fetch price history for {symbol}: {e}"
#     if df is None or df.empty:
#         return f"❌ No price history returned for {symbol}."
#     close_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
#     try:
#         start_p = float(df.iloc[0][close_col])
#         end_p   = float(df.iloc[-1][close_col])
#         ret     = (end_p / start_p - 1) * 100
#     except Exception:
#         start_p = end_p = ret = None
#     lines = [f"## A-Share Price History — {symbol}", f"*Source: AKShare / Eastmoney · {today()}*\n"]
#     if ret is not None:
#         lines += [build_kv_table({"Start Price": f"¥{start_p:,.2f}", "End Price": f"¥{end_p:,.2f}", "Total Return": f"{ret:+.1f}%"}), ""]
#     lines += [df_to_md(df.tail(10), max_rows=10), "", source_footer("AKShare / Eastmoney")]
#     return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ═════════════════════════════════════════════════════════════════════════════

# ── data_sources ──────────────────────────────────────────────────────────────
def handle_data_sources(_):
    return f"""## Market Data Sources — Finance MCP
*{today()}*

---

### 📊 yfinance — Global Markets
Covers US, EU, HK equities. Real-time quotes, financials, analyst estimates, earnings calendar.
⚠️ Unofficial. Rate limits apply. China A-share coverage is unreliable — use AKShare or THS.

### 🇨🇳 AKShare — China Markets
Covers A-share financials (CSRC filings), macro indicators, market indexes, sector P/E.
⚠️ Eastmoney-based quote/history endpoints are BLOCKED by MCP proxy. See disabled tools below.

### 🔍 Tonghuashun Scraper (10jqka.com.cn) — A-Share Fundamentals
Scrapes THS stock pages for EPS, NAV, revenue, analyst ratings, block trades, margin data.
✅ Not blocked. Does NOT return live intraday price (JavaScript-rendered — use web_search instead).

---

### Tool Routing Guide

| Need | Tool |
|---|---|
| US / EU / HK stock quote | `yf_quote` |
| HK stock if yf rate-limited | `web_search` |
| A-share fundamentals + analyst data | `ak_a_share_quote_ths` |
| A-share multi-year financials | `ak_a_share_financials` |
| A-share live price | `web_search("600519 股价 今日")` |
| Chinese macro (GDP, CPI, PMI…) | `ak_macro_china` |
| CSI 300 / SSE index level | `ak_index_quote` |
| Sector P/E (China) | `ak_sector_pe` |
| Prior analysis / cost basis | `analysis_log_read` (portfolio server) |

### Disabled Tools (proxy-blocked)
- `ak_a_share_quote` — push2.eastmoney.com blocked
- `ak_a_share_history` — push2his.eastmoney.com blocked
Handlers are preserved as commented-out stubs in server.py for future re-enabling.

---
*Install: `pip install yfinance akshare mcp`*
"""


# ── yf_quote ──────────────────────────────────────────────────────────────────
def handle_yf_quote(args):
    ticker = args["ticker"].upper()
    try:
        t    = yf.Ticker(ticker)
        info = t.info
    except Exception as e:
        return f"❌ Could not fetch data for {ticker}: {e}"

    name     = safe(info, "longName", default=ticker)
    sector   = safe(info, "sector")
    industry = safe(info, "industry")
    exchange = safe(info, "exchange")
    currency = safe(info, "currency", default="USD")

    price   = safe(info, "currentPrice") or safe(info, "regularMarketPrice")
    prev_cl = safe(info, "previousClose")
    change  = None
    if isinstance(price, (int, float)) and isinstance(prev_cl, (int, float)):
        change = (price - prev_cl) / prev_cl

    mktcap    = info.get("marketCap")
    ev        = info.get("enterpriseValue")
    pe        = info.get("trailingPE")
    fpe       = info.get("forwardPE")
    ev_rev    = info.get("enterpriseToRevenue")
    ev_ebitda = info.get("enterpriseToEbitda")
    pb        = info.get("priceToBook")
    rev       = info.get("totalRevenue")
    ebitda    = info.get("ebitda")
    gm        = info.get("grossMargins")
    om        = info.get("operatingMargins")
    pm        = info.get("profitMargins")
    beta      = info.get("beta")
    w52h      = info.get("fiftyTwoWeekHigh")
    w52l      = info.get("fiftyTwoWeekLow")
    tgt       = info.get("targetMeanPrice")
    rec       = safe(info, "recommendationKey")
    div_yld   = info.get("dividendYield")

    lines = [
        f"## {name} ({ticker})",
        f"*{exchange} · {sector} · {industry} · {today()}*\n",
        "### Price & Market Data",
        build_kv_table({
            f"Price ({currency})":  fmt_num(price, prefix="$"),
            "Day Change":           fmt_pct(change) if change else "N/A",
            "52-Week Range":        f"{fmt_num(w52l, prefix='$')} – {fmt_num(w52h, prefix='$')}",
            "Market Cap":           fmt_usd(mktcap),
            "Enterprise Value":     fmt_usd(ev),
            "Beta":                 fmt_num(beta),
        }),
        "",
        "### Valuation Multiples",
        build_kv_table({
            "P/E (Trailing)": f"{fmt_num(pe)}x",
            "P/E (Forward)":  f"{fmt_num(fpe)}x",
            "EV/Revenue":     f"{fmt_num(ev_rev)}x",
            "EV/EBITDA":      f"{fmt_num(ev_ebitda)}x",
            "P/B":            f"{fmt_num(pb)}x",
        }),
        "",
        "### Financials (TTM)",
        build_kv_table({
            "Revenue":          fmt_usd(rev),
            "EBITDA":           fmt_usd(ebitda),
            "Gross Margin":     fmt_pct(gm),
            "Operating Margin": fmt_pct(om),
            "Net Margin":       fmt_pct(pm),
        }),
        "",
        "### Analyst Coverage",
        build_kv_table({
            "Recommendation":  rec.upper() if isinstance(rec, str) else "N/A",
            "Mean Target":     fmt_num(tgt, prefix="$"),
            "Implied Upside":  fmt_pct((tgt / price - 1) if isinstance(tgt, (int, float)) and isinstance(price, (int, float)) and price else None),
            "Dividend Yield":  fmt_pct(div_yld),
        }),
        "",
        source_footer("yfinance / Yahoo Finance", "Bloomberg/FactSet"),
    ]
    return "\n".join(lines)


# ── yf_financials ─────────────────────────────────────────────────────────────
def handle_yf_financials(args):
    ticker    = args["ticker"].upper()
    period    = args.get("period", "annual")
    statement = args.get("statement", "income")
    try:
        t = yf.Ticker(ticker)
        if period == "annual":
            df = {
                "income":        t.financials,
                "balance_sheet": t.balance_sheet,
                "cashflow":      t.cashflow,
            }.get(statement)
        else:
            df = {
                "income":        t.quarterly_financials,
                "balance_sheet": t.quarterly_balance_sheet,
                "cashflow":      t.quarterly_cashflow,
            }.get(statement)
    except Exception as e:
        return f"❌ Could not fetch financials for {ticker}: {e}"

    if df is None or df.empty:
        return f"❌ No {statement} data found for {ticker}."

    df = df.T
    df.index = [str(i)[:10] for i in df.index]
    label = {"income": "Income Statement", "balance_sheet": "Balance Sheet", "cashflow": "Cash Flow Statement"}[statement]

    return "\n".join([
        f"## {ticker} — {label} ({period.capitalize()})",
        f"*{source_footer('yfinance', 'SEC filings / audited financials')}*\n",
        df_to_md(df.reset_index().rename(columns={"index": "Period"}), max_rows=8),
        "",
        "> All figures in USD.",
    ])


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

    close       = df["Close"]
    start_price = float(close.iloc[0])
    end_price   = float(close.iloc[-1])
    total_ret   = (end_price / start_price - 1)

    return "\n".join([
        f"## {ticker} — Price History ({period}, {interval})",
        f"*Source: yfinance · {today()}*\n",
        "### Summary",
        build_kv_table({
            "Start Price":     f"${start_price:,.2f}",
            "End Price":       f"${end_price:,.2f}",
            "Total Return":    f"{total_ret*100:+.1f}%",
            "Period High":     f"${float(df['High'].max()):,.2f}",
            "Period Low":      f"${float(df['Low'].min()):,.2f}",
            "Avg Daily Volume": f"{float(df['Volume'].mean()):,.0f}",
            "Data Points":     str(len(df)),
        }),
        "",
        "### Recent Data (last 10 sessions)",
        df_to_md(df.tail(10).reset_index(), max_rows=10),
        "",
        source_footer("yfinance / Yahoo Finance", "exchange feeds"),
    ])


# ── yf_peers_comps ────────────────────────────────────────────────────────────
def handle_yf_peers_comps(args):
    tickers = [t.upper() for t in args["tickers"]]
    rows    = []

    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            rows.append({
                "Ticker":    ticker,
                "Name":      (info.get("shortName") or ticker)[:25],
                "EV/EBITDA": fmt_num(info.get("enterpriseToEbitda")) + "x",
                "EV/Rev":    fmt_num(info.get("enterpriseToRevenue")) + "x",
                "P/E (Fwd)": fmt_num(info.get("forwardPE")) + "x",
                "P/B":       fmt_num(info.get("priceToBook")) + "x",
                "EBITDA Mgn":fmt_pct(info.get("ebitdaMargins")),
                "Rev Growth":fmt_pct(info.get("revenueGrowth")),
                "Mkt Cap":   fmt_usd(info.get("marketCap")),
                "Currency":  info.get("currency", "?"),
            })
        except Exception as e:
            rows.append({"Ticker": ticker, "Name": f"Error: {e}"})

    if not rows:
        return "❌ No data returned."

    keys   = ["Ticker", "Name", "EV/EBITDA", "EV/Rev", "P/E (Fwd)", "P/B", "EBITDA Mgn", "Rev Growth", "Mkt Cap", "Currency"]
    header = "| " + " | ".join(keys) + " |"
    sep    = "|" + "|".join(["---"] * len(keys)) + "|"
    body   = ["| " + " | ".join(str(r.get(k, "N/A")) for k in keys) + " |" for r in rows]

    return "\n".join([
        f"## Peer Comps — {', '.join(tickers)}",
        f"*Source: yfinance · {today()}*\n",
        header, sep, *body,
        "",
        "> ⚠️ Currency column shown — do not compare absolute figures across currencies without conversion.",
        source_footer("yfinance / Yahoo Finance", "Bloomberg/FactSet"),
    ])


# ── yf_analyst_estimates ──────────────────────────────────────────────────────
def handle_yf_analyst_estimates(args):
    ticker = args["ticker"].upper()
    try:
        t    = yf.Ticker(ticker)
        info = t.info
    except Exception as e:
        return f"❌ Could not fetch estimates for {ticker}: {e}"

    tgt_mean = info.get("targetMeanPrice")
    tgt_low  = info.get("targetLowPrice")
    tgt_high = info.get("targetHighPrice")
    price    = info.get("currentPrice") or info.get("regularMarketPrice")
    rec      = safe(info, "recommendationKey", default="N/A")
    num_anal = info.get("numberOfAnalystOpinions", "N/A")
    upside   = (tgt_mean / price - 1) if isinstance(tgt_mean, (int, float)) and isinstance(price, (int, float)) and price else None

    return "\n".join([
        f"## {ticker} — Analyst Estimates & Targets",
        f"*Source: yfinance · {today()}*\n",
        build_kv_table({
            "Current Price":  fmt_num(price, prefix="$"),
            "Mean Target":    fmt_num(tgt_mean, prefix="$"),
            "Low Target":     fmt_num(tgt_low, prefix="$"),
            "High Target":    fmt_num(tgt_high, prefix="$"),
            "Implied Upside": fmt_pct(upside),
            "Consensus":      rec.upper() if isinstance(rec, str) else "N/A",
            "# Analysts":     str(num_anal),
            "EPS (Fwd)":      fmt_num(info.get("forwardEps"), prefix="$"),
            "P/E (Fwd)":      f"{fmt_num(info.get('forwardPE'))}x",
        }),
        "",
        source_footer("yfinance / Yahoo Finance", "Bloomberg/FactSet"),
    ])


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

    fy_end = safe(info, "lastFiscalYearEnd", default="N/A")
    fy_end = fy_end[:10] if isinstance(fy_end, str) and len(fy_end) >= 10 else "N/A"

    return "\n".join([
        f"## {ticker} — Earnings Calendar",
        f"*Source: yfinance · {today()}*\n",
        build_kv_table({
            "Next Earnings Date": next_date,
            "Fiscal Year End":    fy_end,
        }),
        "",
        "> ⚠️ Dates are estimates. Confirm via company IR website.",
    ])


# ── ak_a_share_quote_ths ─────────────────────────────────────────────────────
def handle_ak_a_share_quote_ths(args):
    symbol = args["symbol"].strip()
    url    = f"https://stockpage.10jqka.com.cn/{symbol}/"

    try:
        html = fetch_ths_page(symbol)
    except Exception as e:
        return (
            f"❌ Could not fetch data for {symbol} from Tonghuashun: {e}\n\n"
            f"URL attempted: {url}\n"
            f"Tip: Verify the 6-digit symbol is correct (e.g. '600519' for Moutai)."
        )

    def find(pattern, default="N/A"):
        m = re.search(pattern, html, re.DOTALL)
        return m.group(1).strip() if m else default

    name = find(r"<title>([^<（(]+)", symbol)
    name = name.replace("加入自选股", "").strip()

    fundamentals = {
        "每股收益 EPS":          find(r"每股收益[：:][\s\S]*?([\d\.\-]+)元"),
        "每股净资产 NAV/Share":  find(r"每股净资产[：:][\s\S]*?([\d\.\-]+)元"),
        "净利润 Net Profit":     find(r"净利润[：:][\s\S]*?([\d\.亿万]+)元"),
        "净利润增长率":           find(r"净利润增长率[：:][\s\S]*?([\d\.\-\+]+)%") + "%",
        "营业收入 Revenue":      find(r"营业收入[：:][\s\S]*?([\d\.亿万]+)元"),
        "每股现金流 CFO/Share":  find(r"每股现金流[：:][\s\S]*?([\d\.\-]+)元"),
        "每股公积金":            find(r"每股公积金[：:][\s\S]*?([\d\.\-]+)元"),
        "每股未分配利润":         find(r"每股未分配利润[：:][\s\S]*?([\d\.\-]+)元"),
        "总股本 Total Shares":   find(r"总股本[：:][\s\S]*?([\d\.亿万]+)"),
        "流通股 Float Shares":   find(r"流通股[：:][\s\S]*?([\d\.亿万]+)"),
    }

    analyst_summary = find(r"最近60个交易日[，,]([^。<]+)")

    # Block trades
    block_section = ""
    block_match = re.search(r"大宗交易[\s\S]{0,200}?交易日期[\s\S]{0,2000}?融资融券", html)
    if block_match:
        bt_rows = re.findall(
            r"(202\d-\d{2}-\d{2})[\s\S]*?([\d\.]+)元[\s\S]*?([\d\.]+)万元[\s\S]*?([\d\.]+)万股",
            block_match.group(0)
        )
        if bt_rows:
            block_lines = ["| Date | Price (¥) | Amount (万¥) | Volume (万股) |", "|---|---|---|---|"]
            block_lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in bt_rows[:5]]
            block_section = "\n".join(block_lines)

    # Margin data
    margin_bal   = find(r"融资余额[（(]亿元[)）][\s\S]*?([\d\.]+)")
    margin_date  = find(r"(202\d-\d{2}-\d{2})[\s\S]{0,20}融资余额")
    margin_ratio = find(r"融资余额/流通市值[\s\S]*?([\d\.]+%)")
    margin_buy   = find(r"融资买入额[（(]亿元[)）][\s\S]*?([\d\.]+)")

    lines = [
        f"## {name} ({symbol}) — 同花顺基本面数据",
        f"*Source: Tonghuashun (10jqka.com.cn) · {today()}*",
        f"*⚠️ No live price — use web_search('{symbol} 股价 今日') for intraday price.*\n",
        "### 基本面指标 (Fundamentals)",
        build_kv_table(fundamentals),
        "",
        "### 机构评级 (Analyst Consensus — last 60 trading days)",
        analyst_summary if analyst_summary != "N/A" else "_No analyst consensus data found._",
        "",
    ]

    if block_section:
        lines += ["### 大宗交易 (Recent Block Trades)", block_section, ""]

    if margin_bal != "N/A":
        lines += [
            "### 融资融券 (Margin Data)",
            build_kv_table({
                "Date":                      margin_date,
                "融资余额 Margin Balance":    f"¥{margin_bal}亿",
                "融资余额/流通市值":           margin_ratio,
                "融资买入额 Margin Buy":      f"¥{margin_buy}亿",
            }),
            "",
        ]

    lines.append(source_footer("Tonghuashun (同花顺)", "Wind/Bloomberg"))
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

    return "\n".join([
        f"## A-Share Financial Summary — {symbol}",
        f"*Source: AKShare / Tonghuashun (CSRC filings) · {today()}*\n",
        df_to_md(df, max_rows=8),
        "",
        source_footer("AKShare / Tonghuashun (CSRC filings)", "official CSRC filings"),
    ])


# ── ak_macro_china ────────────────────────────────────────────────────────────
MACRO_INDICATOR_MAP = {
    "gdp":               ("macro_china_gdp",                      "China GDP Growth Rate"),
    "cpi":               ("macro_china_cpi_monthly",              "China CPI (Monthly)"),
    "ppi":               ("macro_china_ppi_monthly",              "China PPI (Monthly)"),
    "m2":                ("macro_china_m2_yearly",                "China M2 Money Supply"),
    "pmi_manufacturing": ("macro_china_pmi_yearly",              "China Manufacturing PMI"),
    "pmi_services":      ("macro_china_non_man_pmi",             "China Non-Manufacturing PMI"),
    "retail_sales":      ("macro_china_retail_total",            "China Retail Sales"),
    "industrial_output": ("macro_china_industrial_production_yoy","China Industrial Output YoY"),
    "trade_balance":     ("macro_china_trade_balance",           "China Trade Balance"),
}

def handle_ak_macro_china(args):
    indicator = args["indicator"]
    if indicator not in MACRO_INDICATOR_MAP:
        return f"❌ Unknown indicator: {indicator}. Choose from: {', '.join(MACRO_INDICATOR_MAP)}"

    func_name, label = MACRO_INDICATOR_MAP[indicator]
    try:
        df = getattr(ak, func_name)()
    except AttributeError:
        return f"❌ AKShare function `{func_name}` not found. Try: pip install akshare --upgrade"
    except Exception as e:
        return f"❌ Could not fetch {label}: {e}"

    if df is None or df.empty:
        return f"❌ No data returned for {label}."

    return "\n".join([
        f"## {label}",
        f"*Source: AKShare / NBS · {today()}*\n",
        df_to_md(df.tail(12), max_rows=12),
        "",
        source_footer("AKShare / National Bureau of Statistics (NBS)", "NBS official website"),
    ])


# ── ak_index_quote ────────────────────────────────────────────────────────────
INDEX_MAP = {
    "csi300":         ("000300", "CSI 300"),
    "csi500":         ("000905", "CSI 500"),
    "sse_composite":  ("000001", "SSE Composite"),
    "szse_component": ("399001", "SZSE Component"),
    "chinext":        ("399006", "ChiNext"),
    "star":           ("000688", "STAR Market 50"),
}

def handle_ak_index_quote(args):
    index = args["index"]
    if index not in INDEX_MAP:
        return f"❌ Unknown index: {index}"

    code, label = INDEX_MAP[index]
    prefix = "sh" if code.startswith("0") else "sz"
    try:
        df = ak.stock_zh_index_daily(symbol=f"{prefix}{code}")
    except Exception as e:
        return f"❌ Could not fetch index data for {label}: {e}"

    if df is None or df.empty:
        return f"❌ No data returned for {label}."

    latest  = df.iloc[-1]
    prev    = df.iloc[-2] if len(df) > 1 else None
    try:
        close   = float(latest.get("close", latest.iloc[-1]))
        p_close = float(prev.get("close", prev.iloc[-1])) if prev is not None else None
        chg     = (close / p_close - 1) if p_close else None
    except Exception:
        close = chg = None

    return "\n".join([
        f"## {label} ({code})",
        f"*Source: AKShare · {today()}*\n",
        build_kv_table({
            "Latest Close": fmt_num(close, prefix="¥"),
            "Day Change":   fmt_pct(chg) if chg is not None else "N/A",
        }),
        "",
        "### Recent History (last 10 sessions)",
        df_to_md(df.tail(10), max_rows=10),
        "",
        source_footer("AKShare / Shanghai & Shenzhen Stock Exchange", "exchange official data"),
    ])


# ── ak_sector_pe ─────────────────────────────────────────────────────────────
def handle_ak_sector_pe(args):
    exchange = args.get("exchange", "shanghai")
    label    = "Shanghai (SSE)" if exchange == "shanghai" else "Shenzhen (SZSE)"
    ex_code  = "sh" if exchange == "shanghai" else "sz"

    try:
        df = ak.stock_sector_pe_ratio_cninfo(date=date.today().strftime("%Y%m%d"), symbol=ex_code)
    except Exception as e:
        try:
            df = ak.stock_sector_pe_ratio_cninfo(
                date=date.today().replace(day=1).strftime("%Y%m%d"),
                symbol=ex_code
            )
        except Exception as e2:
            return f"❌ Could not fetch sector P/E for {label}: {e}\nFallback also failed: {e2}"

    if df is None or df.empty:
        return f"❌ No sector P/E data returned for {label}."

    return "\n".join([
        f"## {label} — Sector P/E Ratios",
        f"*Source: AKShare / CNINFO · {today()}*\n",
        df_to_md(df, max_rows=30),
        "",
        source_footer("AKShare / China Securities Information (巨潮资讯)", "Wind/Bloomberg"),
    ])


# ═════════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═════════════════════════════════════════════════════════════════════════════

DISPATCH = {
    "data_sources":          handle_data_sources,
    "yf_quote":              handle_yf_quote,
    "yf_financials":         handle_yf_financials,
    "yf_price_history":      handle_yf_price_history,
    "yf_peers_comps":        handle_yf_peers_comps,
    "yf_analyst_estimates":  handle_yf_analyst_estimates,
    "yf_earnings_calendar":  handle_yf_earnings_calendar,
    "ak_a_share_quote_ths":  handle_ak_a_share_quote_ths,
    "ak_a_share_financials": handle_ak_a_share_financials,
    "ak_macro_china":        handle_ak_macro_china,
    "ak_index_quote":        handle_ak_index_quote,
    "ak_sector_pe":          handle_ak_sector_pe,
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
