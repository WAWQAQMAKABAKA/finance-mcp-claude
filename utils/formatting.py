"""
utils/formatting.py
-------------------
Shared formatting helpers used across all Finance MCP servers.
Import with:  from utils.formatting import today, fmt_num, fmt_pct, safe, df_to_md, build_kv_table, source_footer
"""

from datetime import date


# ── Date ──────────────────────────────────────────────────────────────────────

def today() -> str:
    """Return today's date as ISO string (YYYY-MM-DD)."""
    return date.today().isoformat()


# ── Number formatting ─────────────────────────────────────────────────────────

def fmt_num(val, decimals: int = 2, prefix: str = "", suffix: str = "", na: str = "N/A") -> str:
    """Safely format a numeric value with optional prefix/suffix."""
    try:
        if val is None or (isinstance(val, float) and val != val):  # NaN check
            return na
        return f"{prefix}{val:,.{decimals}f}{suffix}"
    except Exception:
        return na


def fmt_pct(val, na: str = "N/A") -> str:
    """Format a decimal fraction as a percentage string (0.15 → '15.00%')."""
    try:
        if val is None:
            return na
        return f"{val * 100:.2f}%"
    except Exception:
        return na


def fmt_cny(val) -> str:
    """Format a value in CNY with T/B/M suffix."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
        if v >= 1e12: return f"¥{v / 1e12:.2f}T"
        if v >= 1e9:  return f"¥{v / 1e9:.2f}B"
        if v >= 1e6:  return f"¥{v / 1e6:.0f}M"
        return f"¥{v:,.0f}"
    except Exception:
        return "N/A"


def fmt_usd(val) -> str:
    """Format a value in USD with T/B/M suffix."""
    if val is None:
        return "N/A"
    try:
        v = float(val)
        if v >= 1e12: return f"${v / 1e12:.2f}T"
        if v >= 1e9:  return f"${v / 1e9:.2f}B"
        if v >= 1e6:  return f"${v / 1e6:.0f}M"
        return f"${v:,.0f}"
    except Exception:
        return "N/A"


# ── Dict / nested access ──────────────────────────────────────────────────────

def safe(d, *keys, default="N/A"):
    """Safely traverse a nested dict, returning default if any key is missing."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d if d not in (None, "", "None") else default


# ── DataFrame → Markdown ──────────────────────────────────────────────────────

def df_to_md(df, max_rows: int = 10, truncated_note: bool = True) -> str:
    """
    Convert a pandas DataFrame to a markdown table.

    Args:
        df:              DataFrame to render.
        max_rows:        Maximum rows to show. If the DataFrame has more rows,
                         a note is appended (unless truncated_note=False).
        truncated_note:  Whether to append a note when rows are cut off.
    """
    if df is None or df.empty:
        return "_No data returned._"

    total_rows = len(df)
    df = df.head(max_rows).reset_index(drop=True)
    df.columns = [str(c) for c in df.columns]

    header = "| " + " | ".join(df.columns) + " |"
    sep    = "|" + "|".join(["---"] * len(df.columns)) + "|"
    rows   = []
    for _, row in df.iterrows():
        cells = []
        for v in row:
            try:
                cells.append(f"{v:,.2f}" if isinstance(v, float) else str(v)[:40])
            except Exception:
                cells.append("—")
        rows.append("| " + " | ".join(cells) + " |")

    table = "\n".join([header, sep] + rows)

    if truncated_note and total_rows > max_rows:
        table += f"\n\n> ⚠️ Showing {max_rows} of {total_rows} rows."

    return table


# ── Markdown table builders ───────────────────────────────────────────────────

def build_kv_table(data: dict, key_label: str = "Field", val_label: str = "Value") -> str:
    """
    Render a dict as a two-column markdown key-value table.

    Example:
        build_kv_table({"EPS": "51.53", "Revenue": "1,309亿"})
        →  | Field   | Value   |
           |---------|---------|
           | EPS     | 51.53   |
           | Revenue | 1,309亿 |
    """
    if not data:
        return "_No data._"
    lines = [f"| {key_label} | {val_label} |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in data.items()]
    return "\n".join(lines)


# ── Source footer ─────────────────────────────────────────────────────────────

def source_footer(source: str, verify_against: str = "Wind/Bloomberg") -> str:
    """
    Standard disclaimer footer appended to every tool response.

    Args:
        source:          Human-readable source name (e.g. 'AKShare / Tonghuashun').
        verify_against:  What to verify against for precision work.
    """
    return (
        f"> Data sourced from {source}. For research purposes only.\n"
        f"> ⚠️ Verify against {verify_against} before use in client materials."
    )
