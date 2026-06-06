#!/usr/bin/env python3
"""
Finance MCP — Portfolio Server
Manages persistent user state: analysis log, position tracking, session history.

Separate from market-data server intentionally — this server has zero
dependency on yfinance, AKShare, or any external data source. It only
reads and writes local JSON state.

Storage
-------
All data lives in analysis_log.json in the same directory as this file.
Path is overridable via the PORTFOLIO_LOG_PATH environment variable,
which is recommended for containerised or multi-user deployments.

Schema versioning
-----------------
v1 → flat entry: symbol, name, conclusion, cost_basis, stop_loss, etc.
v2 → adds "history": append-only list of dated session summaries.
     Top-level fields always reflect the CURRENT position state.
     History is never overwritten — only appended to.

Migration
---------
migrate_entry() upgrades v1 → v2 automatically on read by adding history: [].
Future migrations registered in MIGRATIONS dict.
"""

import json
import os
import sys
import asyncio
from datetime import date

# ── MCP SDK ───────────────────────────────────────────────────────────────────
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("ERROR: mcp package not found.\nRun: pip install mcp", file=sys.stderr)
    sys.exit(1)

server = Server("finance-portfolio")

# ── utils ─────────────────────────────────────────────────────────────────────
def today() -> str:
    return date.today().isoformat()

def build_kv_table(data: dict, key_label: str = "Field", val_label: str = "Value") -> str:
    if not data:
        return "_No data._"
    lines = [f"| {key_label} | {val_label} |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in data.items()]
    return "\n".join(lines)

# ── Storage ───────────────────────────────────────────────────────────────────
_DEFAULT_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analysis_log.json")
LOG_PATH = os.environ.get("PORTFOLIO_LOG_PATH", _DEFAULT_LOG)

CURRENT_SCHEMA_VERSION = 2

def _load_log() -> dict:
    if not os.path.exists(LOG_PATH):
        return {}
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {sym: migrate_entry(entry) for sym, entry in data.items()}
    except Exception:
        return {}

def _save_log(data: dict) -> None:
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Schema migration ──────────────────────────────────────────────────────────
MIGRATIONS = {
    # v1 → v2: add empty history list
    1: lambda e: {**e, "history": [], "schema_version": 2},
}

def migrate_entry(entry: dict) -> dict:
    """Upgrade an entry through all registered migrations sequentially."""
    version = entry.get("schema_version", 1)
    while version in MIGRATIONS:
        entry   = MIGRATIONS[version](entry)
        version = entry.get("schema_version", version + 1)
    return entry

# ═════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRY
# ═════════════════════════════════════════════════════════════════════════════

TOOLS = [

    Tool(
        name="analysis_log_read",
        description=(
            "Read prior analysis entries from the local log. "
            "Call this at the START of any stock analysis session — before fetching live data. "
            "Pass a symbol to look up one stock: returns current position state, then tells the user "
            "how many prior history sessions exist and asks how many they want to see. "
            "Pass n_history to return that many history entries (most recent first). "
            "Omit symbol entirely to get the full portfolio summary table across all stocks."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock code to look up (e.g. '600519'). Omit to return full portfolio summary."
                },
                "n_history": {
                    "type": "integer",
                    "description": "Number of history entries to show (most recent first). Only used when symbol is provided."
                },
            },
            "required": [],
        },
    ),

    Tool(
        name="analysis_log_save",
        description=(
            "Save or update the current position state for a stock. "
            "Call this at the END of every stock analysis session. "
            "Updates top-level fields (conclusion, cost_basis, stop_loss, etc.) with latest values. "
            "Does NOT touch the history array — use analysis_log_history_append for that. "
            "Always call both this AND analysis_log_history_append at session end."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol":            {"type": "string",  "description": "Stock code or ticker (e.g. '600519', '0700.HK')"},
                "name":              {"type": "string",  "description": "Company name (e.g. '贵州茅台')"},
                "conclusion":        {"type": "string",  "description": "One-line conclusion (e.g. '持有, 等待右侧信号, 止损1314')"},
                "price_at_analysis": {"type": "number",  "description": "Stock price at time of analysis"},
                "cost_basis":        {"type": "number",  "description": "User's average entry / cost basis price"},
                "position_type":     {"type": "string",  "description": "底仓 / 卫星仓 / 观察 / 空仓"},
                "stop_loss":         {"type": "number",  "description": "Hard stop loss price"},
                "target_price":      {"type": "number",  "description": "Take-profit / target price"},
                "notes":             {"type": "string",  "description": "Catalysts, risks, follow-up triggers, technicals"},
            },
            "required": ["symbol", "name", "conclusion"],
        },
    ),

    Tool(
        name="analysis_log_history_append",
        description=(
            "Append a session summary to the history array for a stock. "
            "Call this at the END of every stock analysis session alongside analysis_log_save. "
            "Each entry is a dated record of what was discussed, what signals were noted, "
            "and what conclusion was reached — building a full audit trail of all sessions. "
            "History is append-only — existing entries are never modified or deleted."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol":            {"type": "string", "description": "Stock code (e.g. '600519')"},
                "price_at_analysis": {"type": "number", "description": "Stock price at time of this session"},
                "summary":           {"type": "string", "description": "2-4 sentence summary of what was analysed and discussed this session"},
                "conclusion":        {"type": "string", "description": "One-line conclusion reached this session"},
                "key_signals":       {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-5 key signals, catalysts, or technical levels noted (e.g. ['缠论底背驰未确认', 'MA5/10向下', '止损1314'])"
                },
                "position_change":   {"type": "string", "description": "Any position change made or recommended (e.g. '建卫星仓3%', '止损清仓', '维持底仓不变')"},
            },
            "required": ["symbol", "summary", "conclusion"],
        },
    ),

    Tool(
        name="analysis_log_delete",
        description=(
            "Remove a stock entry and its full history from the analysis log. "
            "Use when a position is fully closed and the stock is no longer being tracked."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock code to remove (e.g. '600519')"},
            },
            "required": ["symbol"],
        },
    ),

]

# ═════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ═════════════════════════════════════════════════════════════════════════════

def handle_analysis_log_read(args: dict) -> str:
    symbol    = args.get("symbol", "").strip().upper()
    n_history = args.get("n_history")
    log       = _load_log()

    if not log:
        return (
            "## Analysis Log — Empty\n"
            f"*Log file: {LOG_PATH}*\n\n"
            "No entries yet. Run a stock analysis and call `analysis_log_save` to populate."
        )

    # ── Single stock lookup ───────────────────────────────────────────────────
    if symbol:
        if symbol not in log:
            return (
                f"## Analysis Log — {symbol} Not Found\n"
                f"*Available: {', '.join(sorted(log.keys()))}*\n\n"
                "No prior analysis on record. Proceeding with a fresh data fetch."
            )

        entry   = log[symbol]
        history = entry.get("history", [])
        h_count = len(history)

        # Always show current position state
        state_fields = {
            k: v for k, v in entry.items()
            if k not in ("schema_version", "history")
        }
        lines = [
            f"## Analysis Log — {symbol} ({entry.get('name', '')})",
            f"*Last analyzed: {entry.get('last_analyzed', 'N/A')}*\n",
            "### Current Position State",
            build_kv_table(state_fields),
            "",
        ]

        # History section
        if h_count == 0:
            lines += ["### Session History", "_No session history recorded yet._", ""]

        elif n_history is None:
            # Count only — ask user how many they want
            lines += [
                "### Session History",
                f"**{h_count} prior session(s) on record** "
                f"(earliest: {history[0].get('date', '?')} · "
                f"latest: {history[-1].get('date', '?')})",
                "",
                f"> How many sessions would you like to see? "
                f"Reply with a number (1–{h_count}) or 'all'.",
                "",
            ]

        else:
            # User specified n — return that many, most recent first
            n        = h_count if str(n_history).lower() == "all" else min(int(n_history), h_count)
            selected = list(reversed(history))[:n]

            lines += [
                f"### Session History — {n} of {h_count} session(s) (most recent first)",
                "",
            ]
            for i, session in enumerate(selected, 1):
                lines += [
                    f"#### Session {i} — {session.get('date', '?')}",
                    build_kv_table({
                        "Price":           str(session.get("price_at_analysis", "N/A")),
                        "Conclusion":      session.get("conclusion", "—"),
                        "Position Change": session.get("position_change", "—"),
                    }),
                    "",
                    f"**Summary:** {session.get('summary', '—')}",
                    "",
                ]
                signals = session.get("key_signals", [])
                if signals:
                    lines += [
                        "**Key Signals:**",
                        *[f"- {s}" for s in signals],
                        "",
                    ]

        return "\n".join(lines)

    # ── Full portfolio summary ────────────────────────────────────────────────
    lines = [
        "## Analysis Log — Portfolio Summary",
        f"*{len(log)} stock(s) tracked · {LOG_PATH}*\n",
        "| Symbol | Name | Last Analyzed | Sessions | Position | Cost Basis | Stop Loss | Target | Conclusion |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for sym, e in sorted(log.items()):
        h_count = len(e.get("history", []))
        lines.append(
            f"| {sym} "
            f"| {e.get('name', '—')} "
            f"| {e.get('last_analyzed', '—')} "
            f"| {h_count} "
            f"| {e.get('position_type', '—')} "
            f"| {e.get('cost_basis', '—')} "
            f"| {e.get('stop_loss', '—')} "
            f"| {e.get('target_price', '—')} "
            f"| {e.get('conclusion', '—')} |"
        )
    return "\n".join(lines)


def handle_analysis_log_save(args: dict) -> str:
    symbol = args["symbol"].strip().upper()
    log    = _load_log()

    # Preserve existing history if entry already exists
    existing_history = log.get(symbol, {}).get("history", [])

    entry = {
        "schema_version":    CURRENT_SCHEMA_VERSION,
        "symbol":            symbol,
        "name":              args.get("name", ""),
        "last_analyzed":     today(),
        "conclusion":        args.get("conclusion", ""),
        "price_at_analysis": args.get("price_at_analysis"),
        "cost_basis":        args.get("cost_basis"),
        "position_type":     args.get("position_type", ""),
        "stop_loss":         args.get("stop_loss"),
        "target_price":      args.get("target_price"),
        "notes":             args.get("notes", ""),
        "history":           existing_history,   # always preserved
    }
    # Strip None and empty-string values except history and schema_version
    entry = {
        k: v for k, v in entry.items()
        if k in ("schema_version", "history") or (v is not None and v != "")
    }
    entry["schema_version"] = CURRENT_SCHEMA_VERSION

    log[symbol] = entry
    _save_log(log)

    h_count = len(existing_history)
    lines = [
        f"## ✅ Analysis Log — Saved: {symbol}",
        f"*Written to: {LOG_PATH}*\n",
        build_kv_table({k: v for k, v in entry.items() if k not in ("schema_version", "history")}),
        "",
        f"> History preserved: {h_count} session(s). "
        f"Call `analysis_log_history_append` to add this session to history.",
        f"> Log contains {len(log)} stock(s): {', '.join(sorted(log.keys()))}",
    ]
    return "\n".join(lines)


def handle_analysis_log_history_append(args: dict) -> str:
    symbol = args["symbol"].strip().upper()
    log    = _load_log()

    if symbol not in log:
        return (
            f"## ❌ History Append Failed — {symbol} Not Found\n"
            f"*Available: {', '.join(sorted(log.keys()))}*\n\n"
            "Call `analysis_log_save` first to create the entry, then append history."
        )

    session = {
        "date":              today(),
        "price_at_analysis": args.get("price_at_analysis"),
        "summary":           args.get("summary", ""),
        "conclusion":        args.get("conclusion", ""),
        "key_signals":       args.get("key_signals", []),
        "position_change":   args.get("position_change", ""),
    }
    # Strip None and empty values
    session = {k: v for k, v in session.items() if v is not None and v != "" and v != []}

    log[symbol].setdefault("history", [])
    log[symbol]["history"].append(session)
    _save_log(log)

    h_count = len(log[symbol]["history"])
    lines = [
        f"## ✅ History Appended — {symbol} ({log[symbol].get('name', '')})",
        f"*Session #{h_count} recorded · {today()}*\n",
        build_kv_table({k: v for k, v in session.items() if k != "key_signals"}),
        "",
    ]
    signals = session.get("key_signals", [])
    if signals:
        lines += ["**Key Signals:**", *[f"- {s}" for s in signals], ""]

    lines.append(f"> Total sessions on record for {symbol}: {h_count}")
    return "\n".join(lines)


def handle_analysis_log_delete(args: dict) -> str:
    symbol = args["symbol"].strip().upper()
    log    = _load_log()

    if symbol not in log:
        return (
            f"## Analysis Log — {symbol} Not Found\n"
            f"*Available: {', '.join(sorted(log.keys()))}*\n\n"
            "Nothing to delete."
        )

    name    = log[symbol].get("name", symbol)
    h_count = len(log[symbol].get("history", []))
    del log[symbol]
    _save_log(log)

    return (
        f"## 🗑️ Analysis Log — Removed: {symbol} ({name})\n"
        f"*Deleted {h_count} session(s) of history.*\n"
        f"*Log now contains {len(log)} stock(s): {', '.join(sorted(log.keys()))}*"
    )


# ═════════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═════════════════════════════════════════════════════════════════════════════

DISPATCH = {
    "analysis_log_read":            handle_analysis_log_read,
    "analysis_log_save":            handle_analysis_log_save,
    "analysis_log_history_append":  handle_analysis_log_history_append,
    "analysis_log_delete":          handle_analysis_log_delete,
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
