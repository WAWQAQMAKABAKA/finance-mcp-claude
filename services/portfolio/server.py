#!/usr/bin/env python3
"""
Finance MCP — Portfolio Server
Manages persistent user state: analysis log, position tracking, watchlist.

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
Every entry carries "schema_version": 1. Migration functions are registered
in MIGRATIONS dict — run migrate_entry() on read to upgrade old entries.
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
# Inline today() to keep this server dependency-free from utils.formatting
# (which requires pandas for df_to_md — we don't need it here).
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

CURRENT_SCHEMA_VERSION = 1

def _load_log() -> dict:
    if not os.path.exists(LOG_PATH):
        return {}
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Migrate any old entries on load
        return {sym: migrate_entry(entry) for sym, entry in data.items()}
    except Exception:
        return {}

def _save_log(data: dict) -> None:
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Schema migration ──────────────────────────────────────────────────────────
# Register migration functions here as the schema evolves.
# Each key is the version the entry is currently AT,
# and the function upgrades it to the next version.
MIGRATIONS = {
    # Example for future use:
    # 1: lambda e: {**e, "new_field": None, "schema_version": 2},
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
        name="analysis_log_save",
        description=(
            "Save or update an analysis entry for a stock to the local analysis log. "
            "Call this at the END of every stock analysis session to persist: "
            "conclusion, price at time of analysis, cost basis, position type, "
            "stop loss, target price, and free-form notes. "
            "Overwrites the existing entry for that symbol if one exists. "
            "Use so future sessions have full context without re-fetching or re-analysing."
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
        name="analysis_log_read",
        description=(
            "Read prior analysis entries from the local log. "
            "Call this at the START of any stock analysis session — before fetching live data — "
            "so Claude knows the user's cost basis, stop loss, position type, and prior conclusion. "
            "Pass a symbol to look up one stock. Omit symbol to get the full portfolio summary table."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock code to look up (e.g. '600519'). Omit to return all entries."
                },
            },
            "required": [],
        },
    ),

    Tool(
        name="analysis_log_delete",
        description=(
            "Remove a stock entry from the analysis log. "
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

def handle_analysis_log_save(args: dict) -> str:
    symbol = args["symbol"].strip().upper()
    log    = _load_log()

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
    }
    # Strip None and empty-string values to keep JSON clean
    entry = {k: v for k, v in entry.items() if v is not None and v != ""}
    # Always keep schema_version even if 0/falsy
    entry["schema_version"] = CURRENT_SCHEMA_VERSION

    log[symbol] = entry
    _save_log(log)

    lines = [
        f"## ✅ Analysis Log — Saved: {symbol}",
        f"*Written to: {LOG_PATH}*\n",
        build_kv_table(entry),
        "",
        f"> Log now contains {len(log)} stock(s): {', '.join(sorted(log.keys()))}",
    ]
    return "\n".join(lines)


def handle_analysis_log_read(args: dict) -> str:
    symbol = args.get("symbol", "").strip().upper()
    log    = _load_log()

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
        entry = log[symbol]
        lines = [
            f"## Analysis Log — {symbol} ({entry.get('name', '')})",
            f"*Last analyzed: {entry.get('last_analyzed', 'N/A')} · "
            f"Schema v{entry.get('schema_version', 1)}*\n",
            build_kv_table({k: v for k, v in entry.items() if k != "schema_version"}),
        ]
        return "\n".join(lines)

    # ── Full portfolio summary ────────────────────────────────────────────────
    lines = [
        "## Analysis Log — Portfolio Summary",
        f"*{len(log)} stock(s) tracked · {LOG_PATH}*\n",
        "| Symbol | Name | Last Analyzed | Position | Cost Basis | Stop Loss | Target | Conclusion |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for sym, e in sorted(log.items()):
        lines.append(
            f"| {sym} "
            f"| {e.get('name', '—')} "
            f"| {e.get('last_analyzed', '—')} "
            f"| {e.get('position_type', '—')} "
            f"| {e.get('cost_basis', '—')} "
            f"| {e.get('stop_loss', '—')} "
            f"| {e.get('target_price', '—')} "
            f"| {e.get('conclusion', '—')} |"
        )
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

    name = log[symbol].get("name", symbol)
    del log[symbol]
    _save_log(log)

    return (
        f"## 🗑️ Analysis Log — Removed: {symbol} ({name})\n"
        f"*Log now contains {len(log)} stock(s): {', '.join(sorted(log.keys()))}*"
    )


# ═════════════════════════════════════════════════════════════════════════════
# DISPATCH
# ═════════════════════════════════════════════════════════════════════════════

DISPATCH = {
    "analysis_log_save":   handle_analysis_log_save,
    "analysis_log_read":   handle_analysis_log_read,
    "analysis_log_delete": handle_analysis_log_delete,
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
