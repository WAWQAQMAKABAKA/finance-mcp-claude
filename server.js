import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

// ── paths ────────────────────────────────────────────────────────────────────
const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);

// ── skill loader helper ───────────────────────────────────────────────────────
const loadSkill = (slug) =>
  fs.readFileSync(path.join(__dirname, "skills", slug, "SKILL.md"), "utf-8");

// ── load all skills ───────────────────────────────────────────────────────────
const skills = {
  competitiveAnalysis:        loadSkill("competitive-analysis"),
  compsTable:                 loadSkill("comps-table"),
  dcfModel:                   loadSkill("dcf-model"),
  lboModel:                   loadSkill("lbo-model"),
  earningsSnapshot:           loadSkill("earnings-snapshot"),
  onePager:                   loadSkill("one-pager"),
  pitchDeck:                  loadSkill("pitch-deck"),
  mergerAccretionDilution:    loadSkill("merger-accretion-dilution"),
  icMemo:                     loadSkill("ic-memo"),
  waccCalculator:             loadSkill("wacc-calculator"),
  footballField:              loadSkill("football-field"),
};

console.error("Finance MCP — skills loaded:", Object.keys(skills).join(", "));

// ── server ───────────────────────────────────────────────────────────────────
const server = new Server(
  { name: "finance-mcp", version: "2.0.0" },
  { capabilities: { tools: {} } }
);

// ═════════════════════════════════════════════════════════════════════════════
// TOOL REGISTRY
// ═════════════════════════════════════════════════════════════════════════════

const TOOLS = [

  // ── YOUR ORIGINAL TOOL ────────────────────────────────────────────────────
  {
    name: "competitive_analysis",
    description:
      "Strategic competitive landscape and company analysis across industries and markets. " +
      "Covers market structure, positioning, moats, growth quality, disruption risk, and whitespace.",
    inputSchema: {
      type: "object",
      properties: {
        industry:       { type: "string",  description: "Industry, sector, or market being analyzed" },
        companies:      { type: "array",   description: "Companies relevant to the landscape", items: { type: "string" } },
        geography:      { type: "string",  description: "Geographic focus: Global, US, Europe, China, etc." },
        focus:          { type: "string",  description: "Analytical focus: AI, pricing, margins, SaaS, etc." },
        analysis_depth: { type: "string",  description: "Depth: brief | standard | deep" },
      },
      required: ["industry"],
    },
  },

  // ── EQUITY RESEARCH ───────────────────────────────────────────────────────
  {
    name: "comps_table",
    description:
      "Build a comparable company analysis (trading comps) table with mean/median benchmarks. " +
      "Use for /comps, peer benchmarking, or valuation context.",
    inputSchema: {
      type: "object",
      properties: {
        target_company:    { type: "string", description: "Company being valued" },
        peers: {
          type: "array",
          description: "Peer companies with multiples",
          items: {
            type: "object",
            properties: {
              name:             { type: "string" },
              ev_ebitda:        { type: "number", description: "EV/EBITDA" },
              ev_revenue:       { type: "number", description: "EV/Revenue" },
              pe_ratio:         { type: "number", description: "P/E" },
              price_book:       { type: "number", description: "P/B" },
              ebitda_margin:    { type: "number", description: "EBITDA margin %" },
              revenue_growth:   { type: "number", description: "Revenue growth % YoY" },
            },
            required: ["name"],
          },
        },
        target_multiples: {
          type: "object",
          description: "Target company multiples for benchmarking",
          properties: {
            ev_ebitda:      { type: "number" },
            ev_revenue:     { type: "number" },
            pe_ratio:       { type: "number" },
            price_book:     { type: "number" },
            ebitda_margin:  { type: "number" },
            revenue_growth: { type: "number" },
          },
        },
      },
      required: ["target_company", "peers"],
    },
  },

  {
    name: "dcf_model",
    description:
      "Run a Discounted Cash Flow (DCF) valuation model. Returns intrinsic value per share, " +
      "implied upside/downside, and a WACC × terminal growth sensitivity table. Use for /dcf.",
    inputSchema: {
      type: "object",
      properties: {
        company:         { type: "string" },
        revenue_base:    { type: "number", description: "Current year revenue ($M)" },
        ebitda_margin:   { type: "number", description: "EBITDA margin (0–1)" },
        revenue_cagr:    { type: "number", description: "5-yr revenue CAGR (0–1)" },
        capex_pct:       { type: "number", description: "CapEx % of revenue (0–1)", default: 0.05 },
        tax_rate:        { type: "number", default: 0.25 },
        wacc:            { type: "number", default: 0.10 },
        terminal_growth: { type: "number", default: 0.025 },
        net_debt:        { type: "number", description: "$M (negative = net cash)", default: 0 },
        shares_out:      { type: "number", description: "Diluted shares (M)", default: 100 },
        current_price:   { type: "number", description: "Current price ($)", default: 0 },
      },
      required: ["company", "revenue_base", "ebitda_margin", "revenue_cagr"],
    },
  },

  {
    name: "lbo_model",
    description:
      "Run a leveraged buyout (LBO) model. Returns IRR and MOIC across exit multiples and leverage. " +
      "Use for /lbo, sponsor deal screening, or M&A advisory.",
    inputSchema: {
      type: "object",
      properties: {
        company:        { type: "string" },
        entry_ev:       { type: "number", description: "Entry EV ($M)" },
        entry_ebitda:   { type: "number", description: "Entry EBITDA ($M)" },
        ebitda_growth:  { type: "number", default: 0.08 },
        debt_pct:       { type: "number", description: "Debt % of EV (0–1)", default: 0.60 },
        interest_rate:  { type: "number", default: 0.07 },
        debt_amort_pct: { type: "number", description: "Annual debt amortization % (0–1)", default: 0.05 },
        hold_period:    { type: "integer", default: 5 },
        exit_multiples: { type: "array", items: { type: "number" }, default: [7,8,9,10,11] },
        mgmt_fees_pct:  { type: "number", default: 0.02 },
      },
      required: ["company", "entry_ev", "entry_ebitda"],
    },
  },

  {
    name: "earnings_snapshot",
    description:
      "Generate a post-earnings beat/miss analysis with guidance context and key investor questions. " +
      "Use for /earnings commands or earnings review workflows.",
    inputSchema: {
      type: "object",
      properties: {
        company:      { type: "string" },
        quarter:      { type: "string", description: "e.g. Q1 2025" },
        report_date:  { type: "string", description: "YYYY-MM-DD" },
        actuals: {
          type: "object",
          properties: {
            revenue:      { type: "number", description: "$M" },
            gross_profit: { type: "number" },
            ebitda:       { type: "number" },
            ebit:         { type: "number" },
            eps:          { type: "number" },
          },
        },
        estimates:     { type: "object", description: "Consensus estimates (same keys as actuals)" },
        guidance: {
          type: "object",
          properties: {
            revenue_low: { type: "number" }, revenue_high: { type: "number" },
            ebitda_low:  { type: "number" }, ebitda_high:  { type: "number" },
            eps_low:     { type: "number" }, eps_high:     { type: "number" },
          },
        },
        prior_year:      { type: "object", description: "Prior year same-quarter actuals" },
        analyst_rating:  { type: "string" },
        price_target:    { type: "number" },
      },
      required: ["company", "quarter", "actuals"],
    },
  },

  {
    name: "one_pager",
    description:
      "Generate a one-page company tearsheet with business description, financials, " +
      "valuation, investment thesis, risks, and catalysts. Use for /one-pager or meeting prep.",
    inputSchema: {
      type: "object",
      properties: {
        company:            { type: "string" },
        ticker:             { type: "string" },
        sector:             { type: "string" },
        description:        { type: "string", description: "2-3 sentence business description" },
        market_cap:         { type: "number", description: "$M" },
        enterprise_value:   { type: "number", description: "$M" },
        revenue_ttm:        { type: "number", description: "TTM Revenue $M" },
        ebitda_ttm:         { type: "number", description: "TTM EBITDA $M" },
        net_debt:           { type: "number", description: "$M" },
        key_multiples: {
          type: "object",
          properties: {
            ev_ebitda:  { type: "number" },
            ev_revenue: { type: "number" },
            pe_ratio:   { type: "number" },
          },
        },
        investment_thesis:  { type: "string" },
        key_risks:          { type: "string" },
        catalysts:          { type: "string" },
        analyst_rating:     { type: "string" },
        price_target:       { type: "number" },
      },
      required: ["company", "description"],
    },
  },

  // ── INVESTMENT BANKING ────────────────────────────────────────────────────
  {
    name: "pitch_deck_outline",
    description:
      "Generate a full investment banking pitch deck outline with section scaffolding. " +
      "Covers M&A, IPO, Follow-On, Debt Advisory, Restructuring, and Strategic Review. Use for /pitch.",
    inputSchema: {
      type: "object",
      properties: {
        deal_type: {
          type: "string",
          enum: ["M&A Buy-Side","M&A Sell-Side","IPO","Follow-On","Debt Advisory","Restructuring","Strategic Review"],
        },
        client:      { type: "string" },
        target:      { type: "string", description: "Target company (M&A) or N/A" },
        deal_size:   { type: "number", description: "Indicative deal size ($M)" },
        sector:      { type: "string" },
        key_themes:  { type: "string", description: "2-3 core deal themes" },
        firm_name:   { type: "string", default: "[Your Firm]" },
        include_sections: {
          type: "array",
          items: {
            type: "string",
            enum: [
              "Situation Overview","Strategic Rationale","Target Overview","Market Analysis",
              "Valuation Analysis","Transaction Structure","Financing Overview","Pro Forma Impact",
              "Process & Timeline","Management Considerations","Risk Factors","Appendix",
            ],
          },
        },
      },
      required: ["deal_type", "client", "sector"],
    },
  },

  {
    name: "merger_accretion_dilution",
    description:
      "Run a merger accretion/dilution analysis. Returns EPS impact, pro forma P&L, " +
      "and breakeven premium. Use for M&A advisory and fairness opinions.",
    inputSchema: {
      type: "object",
      properties: {
        acquirer: {
          type: "object",
          properties: {
            name:       { type: "string" },
            net_income: { type: "number", description: "$M" },
            shares_out: { type: "number", description: "M shares" },
            eps:        { type: "number" },
            market_cap: { type: "number", description: "$M" },
          },
          required: ["name","net_income","shares_out","eps"],
        },
        target: {
          type: "object",
          properties: {
            name:          { type: "string" },
            net_income:    { type: "number" },
            shares_out:    { type: "number" },
            eps:           { type: "number" },
            offer_price:   { type: "number" },
            current_price: { type: "number" },
          },
          required: ["name","net_income","shares_out","offer_price"],
        },
        deal_structure: {
          type: "object",
          properties: {
            cash_pct:       { type: "number", default: 0.5 },
            stock_pct:      { type: "number", default: 0.5 },
            synergies:      { type: "number", description: "Annual run-rate synergies ($M)", default: 0 },
            synergy_ramp:   { type: "number", default: 2 },
            financing_rate: { type: "number", default: 0.06 },
            tax_rate:       { type: "number", default: 0.25 },
          },
        },
      },
      required: ["acquirer","target"],
    },
  },

  {
    name: "ic_memo_template",
    description:
      "Generate an Investment Committee memo template with all standard sections. " +
      "Use for /ic-memo or internal deal approval workflows.",
    inputSchema: {
      type: "object",
      properties: {
        deal_name:      { type: "string" },
        deal_type:      { type: "string", description: "e.g. M&A, Growth Equity, Buyout" },
        sector:         { type: "string" },
        target_company: { type: "string" },
        deal_size:      { type: "number", description: "$M" },
        entry_multiple: { type: "number", description: "EV/EBITDA" },
        target_irr:     { type: "number", description: "Target return (0–1)" },
        hold_period:    { type: "integer", description: "Years" },
        thesis:         { type: "string" },
        key_risks:      { type: "string" },
        committee_date: { type: "string", description: "YYYY-MM-DD" },
        deal_lead:      { type: "string" },
      },
      required: ["deal_name","deal_type","target_company"],
    },
  },

  // ── UTILITIES ─────────────────────────────────────────────────────────────
  {
    name: "wacc_calculator",
    description:
      "Calculate WACC from first principles: CAPM cost of equity + after-tax cost of debt. " +
      "Returns blended WACC. Use as a precursor to DCF or LBO.",
    inputSchema: {
      type: "object",
      properties: {
        company:              { type: "string" },
        beta:                 { type: "number" },
        risk_free_rate:       { type: "number" },
        equity_risk_premium:  { type: "number", default: 0.055 },
        cost_of_debt:         { type: "number" },
        tax_rate:             { type: "number", default: 0.25 },
        equity_weight:        { type: "number" },
        debt_weight:          { type: "number" },
        size_premium:         { type: "number", default: 0 },
      },
      required: ["company","beta","risk_free_rate","cost_of_debt","equity_weight","debt_weight"],
    },
  },

  {
    name: "football_field",
    description:
      "Generate a football field valuation summary comparing methodologies side-by-side " +
      "(Trading Comps, Precedent Transactions, DCF, LBO, 52-Week Range, Analyst Targets). " +
      "Standard for fairness opinions and board presentations.",
    inputSchema: {
      type: "object",
      properties: {
        company:      { type: "string" },
        current_price:{ type: "number", description: "Current share price ($)" },
        shares_out:   { type: "number", description: "Diluted shares (M)" },
        net_debt:     { type: "number", description: "$M" },
        methodologies: {
          type: "array",
          items: {
            type: "object",
            properties: {
              method:  { type: "string" },
              ev_low:  { type: "number", description: "Low EV estimate ($M)" },
              ev_high: { type: "number", description: "High EV estimate ($M)" },
              notes:   { type: "string" },
            },
            required: ["method","ev_low","ev_high"],
          },
        },
      },
      required: ["company","shares_out","net_debt","methodologies"],
    },
  },

  {
    name: "list_tools",
    description: "List all available finance tools with descriptions and slash command mappings.",
    inputSchema: { type: "object", properties: {} },
  },
];

// ═════════════════════════════════════════════════════════════════════════════
// TOOL HANDLERS
// ═════════════════════════════════════════════════════════════════════════════

const now = () => new Date().toISOString().slice(0, 10);

function avg(arr) { return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null; }
function median(arr) {
  if (!arr.length) return null;
  const s = [...arr].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 === 0 ? (s[m - 1] + s[m]) / 2 : s[m];
}
function irr(equity_in, equity_out, n) {
  let r = 0.20;
  for (let i = 0; i < 200; i++) {
    const f  = equity_in - equity_out / Math.pow(1 + r, n);
    const fp = equity_out * n / Math.pow(1 + r, n + 1);
    const r2 = r + f / fp;
    if (Math.abs(r2 - r) < 1e-9) return r2;
    r = r2;
  }
  return r;
}

// ── Each handler now injects its SKILL.md as the analytical framework ─────────

function handleCompetitiveAnalysis(args) {
  const industry  = args.industry || "Unknown Industry";
  const companies = args.companies || [];
  const geography = args.geography || "Global";
  const focus     = args.focus || "overall competitive strategy";
  const depth     = args.analysis_depth || "standard";

  const formattedCompanies = companies.length > 0
    ? companies.map(c => `- ${c}`).join("\n")
    : "No companies explicitly provided. Identify major competitors dynamically.";

  const depthInstructions = {
    brief:    "Provide a concise high-level overview with key strategic insights only.",
    deep:     "Provide highly detailed strategic analysis covering industry structure, competitor taxonomy, moat analysis, disruption risks, and long-term market implications.",
    standard: "Provide balanced professional analysis with strategic depth and concise reasoning.",
  };

  return `${skills.competitiveAnalysis}

# User Request

Industry: ${industry}
Companies:\n${formattedCompanies}
Geography: ${geography}
Focus: ${focus}
Depth: ${depth}

${depthInstructions[depth] || depthInstructions.standard}

Deliver professional investment-style analysis. Avoid shallow summaries and generic comparisons.`;
}

function handleCompsTable(args) {
  const target  = args.target_company;
  const peers   = args.peers || [];
  const tm      = args.target_multiples || {};
  const keys    = ["ev_ebitda","ev_revenue","pe_ratio","price_book","ebitda_margin","revenue_growth"];
  const labels  = ["EV/EBITDA","EV/Revenue","P/E","P/B","EBITDA Mgn%","Rev Gr%"];
  const pctKeys = new Set(["ebitda_margin","revenue_growth"]);

  const fmtVal = (k, v) => v == null ? "—" : pctKeys.has(k) ? `${v.toFixed(1)}%` : `${v.toFixed(1)}x`;
  const statsRow = (label, fn) => [label, ...keys.map(k => fmtVal(k, fn(peers.map(p => p[k]).filter(v => v != null))))];

  const rows      = peers.map(p => [p.name, ...keys.map(k => fmtVal(k, p[k]))]);
  const meanRow   = statsRow("Mean", avg);
  const medianRow = statsRow("Median", median);
  const divider   = Array(keys.length + 1).fill("—");

  const lines = [
    `${skills.compsTable}\n`,
    `---\n## Output\n`,
    `## Comparable Company Analysis — ${target}`,
    `*${now()} · ${peers.length} peer(s)*\n`,
    `| Company | ${labels.join(" | ")} |`,
    `|---|${"---|".repeat(labels.length)}`,
    ...rows.map(r => `| ${r.join(" | ")} |`),
    `| ${divider.join(" | ")} |`,
    `| ${meanRow.join(" | ")} |`,
    `| ${medianRow.join(" | ")} |`,
  ];

  if (Object.keys(tm).length) {
    const tRow = [`▶ ${target} (Current)`, ...keys.map(k => fmtVal(k, tm[k]))];
    lines.push(`| ${divider.join(" | ")} |`, `| ${tRow.join(" | ")} |`);
  }

  lines.push("\n> Verify all multiples against live market data before use in client materials.");
  return lines.join("\n");
}

function handleDcf(args) {
  const { company, revenue_base: rev0, ebitda_margin: margin, revenue_cagr: cagr } = args;
  const capex = args.capex_pct ?? 0.05;
  const tax   = args.tax_rate  ?? 0.25;
  const wacc  = args.wacc      ?? 0.10;
  const tgr   = args.terminal_growth ?? 0.025;
  const nd    = args.net_debt  ?? 0;
  const shr   = args.shares_out ?? 100;
  const price = args.current_price ?? 0;

  const fcfs = [], revs = [], pvs = [];
  for (let yr = 1; yr <= 5; yr++) {
    const rev = rev0 * Math.pow(1 + cagr, yr);
    const fcf = rev * margin * (1 - tax) - rev * capex;
    revs.push(rev); fcfs.push(fcf); pvs.push(fcf / Math.pow(1 + wacc, yr));
  }

  const tvPv = (fcfs[4] * (1 + tgr) / (wacc - tgr)) / Math.pow(1 + wacc, 5);
  const ev   = pvs.reduce((a,b) => a+b, 0) + tvPv;
  const eq   = ev - nd;
  const ps   = shr ? eq / shr : 0;
  const upside = price ? ((ps / price - 1) * 100).toFixed(1) : null;

  const waccRange = [wacc - 0.01, wacc, wacc + 0.01];
  const tgrRange  = [tgr - 0.005, tgr, tgr + 0.005];

  const lines = [
    `${skills.dcfModel}\n`,
    `---\n## Output\n`,
    `## DCF Valuation — ${company}`,
    `*${now()} · Base case*\n`,
    "### Assumptions",
    `| Parameter | Value |`,`|---|---|`,
    `| Revenue (Base) | $${rev0.toLocaleString()}M |`,
    `| Revenue CAGR | ${(cagr*100).toFixed(1)}% |`,
    `| EBITDA Margin | ${(margin*100).toFixed(1)}% |`,
    `| WACC | ${(wacc*100).toFixed(1)}% |`,
    `| Terminal Growth | ${(tgr*100).toFixed(1)}% |`,
    "",
    "### Projected FCFs ($M)",
    "| Year | Revenue | EBITDA | FCF | PV(FCF) |","|---|---|---|---|---|",
    ...revs.map((r,i) => `| Y${i+1} | $${Math.round(r).toLocaleString()} | $${Math.round(r*margin).toLocaleString()} | $${Math.round(fcfs[i]).toLocaleString()} | $${Math.round(pvs[i]).toLocaleString()} |`),
    "",
    "### Valuation Summary",
    `| | $M |`,`|---|---|`,
    `| PV of FCFs | $${Math.round(pvs.reduce((a,b)=>a+b,0)).toLocaleString()} |`,
    `| PV of Terminal Value | $${Math.round(tvPv).toLocaleString()} |`,
    `| **Enterprise Value** | **$${Math.round(ev).toLocaleString()}** |`,
    `| Less: Net Debt | ($${Math.round(nd).toLocaleString()}) |`,
    `| **Implied Share Price** | **$${ps.toFixed(2)}** |`,
    upside ? `| Upside vs. $${price.toFixed(2)} | ${upside > 0 ? "+" : ""}${upside}% |` : "",
    "",
    "### Sensitivity — Implied Share Price ($)",
    `| WACC \\ TGR |${tgrRange.map(t => ` ${(t*100).toFixed(1)}% |`).join("")}`,
    `|---|${"---|".repeat(tgrRange.length)}`,
    ...waccRange.map(w => {
      const cells = tgrRange.map(t => {
        if (w <= t) return "N/A";
        const tv2  = fcfs[4] * (1+t) / (w-t);
        const pvT2 = tv2 / Math.pow(1+w, 5);
        const pvF2 = fcfs.reduce((s,f,i) => s + f / Math.pow(1+w,i+1), 0);
        return `$${((pvF2 + pvT2 - nd) / shr).toFixed(2)}`;
      });
      return `| **${(w*100).toFixed(1)}%** | ${cells.join(" | ")} |`;
    }),
    "",
    "> ⚠️ Verify all inputs against audited financials and live market data before use in client materials.",
  ];
  return lines.filter(l => l !== "").join("\n");
}

function handleLbo(args) {
  const { company, entry_ev, entry_ebitda } = args;
  const ebitdaGrowth = args.ebitda_growth  ?? 0.08;
  const debtPct      = args.debt_pct       ?? 0.60;
  const intRate      = args.interest_rate  ?? 0.07;
  const amortPct     = args.debt_amort_pct ?? 0.05;
  const hold         = args.hold_period    ?? 5;
  const exitMults    = args.exit_multiples ?? [7,8,9,10,11];
  const mgmtFee      = args.mgmt_fees_pct  ?? 0.02;

  const totalDebt = entry_ev * debtPct;
  const equityIn  = entry_ev * (1 - debtPct);
  const ebitdas   = [];
  let debtBal = totalDebt;
  for (let yr = 0; yr < hold; yr++) {
    ebitdas.push(entry_ebitda * Math.pow(1 + ebitdaGrowth, yr + 1));
    debtBal = Math.max(0, debtBal * (1 - amortPct));
  }
  const exitDebt = debtBal;
  const mgmtCost = entry_ev * mgmtFee * hold;

  const irrRow  = ["**IRR**"];
  const moicRow = ["**MOIC**"];
  for (const em of exitMults) {
    const exitEq = Math.max(0, ebitdas[hold-1] * em - exitDebt) - mgmtCost;
    moicRow.push(`${(exitEq / equityIn).toFixed(2)}x`);
    try { irrRow.push(`${(irr(equityIn, exitEq, hold) * 100).toFixed(1)}%`); }
    catch { irrRow.push("N/A"); }
  }

  return [
    `${skills.lboModel}\n`,
    `---\n## Output\n`,
    `## LBO Analysis — ${company}`,
    `*${now()} · ${hold}-year hold*\n`,
    "### Transaction Summary",
    `| | |`,`|---|---|`,
    `| Entry EV | $${Math.round(entry_ev).toLocaleString()}M |`,
    `| Entry EV/EBITDA | ${(entry_ev/entry_ebitda).toFixed(1)}x |`,
    `| Total Debt | $${Math.round(totalDebt).toLocaleString()}M (${(debtPct*100).toFixed(0)}%) |`,
    `| Equity Invested | $${Math.round(equityIn).toLocaleString()}M |`,
    `| Exit Debt | $${Math.round(exitDebt).toLocaleString()}M |`,
    "",
    "### Returns Matrix",
    `| | ${exitMults.map(m => `${m}x`).join(" | ")} |`,
    `|---|${"---|".repeat(exitMults.length)}`,
    `| ${irrRow.join(" | ")} |`,
    `| ${moicRow.join(" | ")} |`,
    "",
    "> ⚠️ Simplified model. Verify assumptions against current financing market conditions.",
  ].join("\n");
}

function handleEarnings(args) {
  const { company, quarter } = args;
  const act  = args.actuals   || {};
  const est  = args.estimates || {};
  const guid = args.guidance  || {};
  const py   = args.prior_year || {};

  const beat = k => {
    const a = act[k], e = est[k];
    if (a == null || e == null) return "—";
    const d = (a/e - 1) * 100;
    return `${d >= 0 ? "✅" : "❌"} ${d >= 0 ? "+" : ""}${d.toFixed(1)}%`;
  };
  const yoy = k => {
    const a = act[k], p = py[k];
    if (a == null || p == null) return "—";
    return `${((a/p-1)*100).toFixed(1)}%`;
  };

  const metrics = [
    ["Revenue ($M)","revenue"],["Gross Profit ($M)","gross_profit"],
    ["EBITDA ($M)","ebitda"],["EBIT ($M)","ebit"],["EPS ($)","eps"],
  ];

  const lines = [
    `${skills.earningsSnapshot}\n`,
    `---\n## Output\n`,
    `## ${company} — ${quarter} Earnings Snapshot`,
    `*Date: ${args.report_date||"N/A"} · Rating: ${args.analyst_rating||"N/A"}${args.price_target ? ` · PT: $${args.price_target.toFixed(2)}` : ""}*\n`,
    "### Results vs. Consensus",
    "| Metric | Actual | Estimate | Beat / Miss | YoY |","|---|---|---|---|---|",
    ...metrics.map(([label,k]) => `| ${label} | ${act[k]!=null?`$${act[k].toFixed(1)}`:"—"} | ${est[k]!=null?`$${est[k].toFixed(1)}`:"—"} | ${beat(k)} | ${yoy(k)} |`),
  ];

  if (Object.keys(guid).length) {
    lines.push("","### Management Guidance");
    if (guid.revenue_low||guid.revenue_high) lines.push(`- **Revenue:** $${(guid.revenue_low||0).toLocaleString()}M – $${(guid.revenue_high||0).toLocaleString()}M`);
    if (guid.ebitda_low||guid.ebitda_high)   lines.push(`- **EBITDA:** $${(guid.ebitda_low||0).toLocaleString()}M – $${(guid.ebitda_high||0).toLocaleString()}M`);
    if (guid.eps_low||guid.eps_high)         lines.push(`- **EPS:** $${(guid.eps_low||0).toFixed(2)} – $${(guid.eps_high||0).toFixed(2)}`);
  }

  lines.push(
    "","### Key Investor Questions",
    "1. **Beat quality** — Organic or one-time?",
    "2. **Margin trajectory** — Structural or temporary?",
    "3. **Guidance credibility** — Conservative or aggressive?",
    "4. **Capital allocation** — Buybacks, dividend, M&A?",
    "5. **Thesis check** — Does this print confirm or challenge the investment case?",
  );
  return lines.join("\n");
}

function handleOnePager(args) {
  const { company } = args;
  const km   = args.key_multiples || {};
  const date = new Date().toLocaleDateString("en-US",{month:"long",day:"numeric",year:"numeric"});

  const lines = [
    `${skills.onePager}\n`,
    `---\n## Output\n`,
    `# ${company}${args.ticker ? ` (${args.ticker})` : ""}`,
    `**Sector:** ${args.sector||"—"}  |  **Rating:** ${args.analyst_rating||"—"}${args.price_target ? `  |  **PT:** $${args.price_target.toFixed(2)}` : ""}`,
    `*One-Pager · ${date}*\n---`,
    "## Business Description", args.description,
    "","## Financial Summary (TTM)","| Metric | Value |","|---|---|",
    ...["market_cap","enterprise_value","revenue_ttm","ebitda_ttm","net_debt"].flatMap(k => {
      const labels = {market_cap:"Market Cap",enterprise_value:"Enterprise Value",revenue_ttm:"Revenue",ebitda_ttm:"EBITDA",net_debt:"Net Debt / (Net Cash)"};
      return args[k] != null ? [`| ${labels[k]} | $${Math.round(args[k]).toLocaleString()}M |`] : [];
    }),
  ];
  if (Object.keys(km).length) {
    lines.push("","## Key Multiples","| Multiple | Value |","|---|---|");
    if (km.ev_ebitda)  lines.push(`| EV/EBITDA  | ${km.ev_ebitda.toFixed(1)}x |`);
    if (km.ev_revenue) lines.push(`| EV/Revenue | ${km.ev_revenue.toFixed(1)}x |`);
    if (km.pe_ratio)   lines.push(`| P/E        | ${km.pe_ratio.toFixed(1)}x |`);
  }
  lines.push(
    "","## Investment Thesis", args.investment_thesis||"[Analyst to complete]",
    "","## Key Risks",        args.key_risks||"[Analyst to complete]",
    "","## Catalysts",        args.catalysts||"[Analyst to complete]",
    "","---","*For informational purposes only. Does not constitute investment advice.*",
  );
  return lines.join("\n");
}

function handlePitch(args) {
  const { deal_type, client, sector } = args;
  const sections = args.include_sections || [
    "Situation Overview","Strategic Rationale","Target Overview","Market Analysis",
    "Valuation Analysis","Transaction Structure","Financing Overview","Process & Timeline","Appendix",
  ];
  const firm = args.firm_name || "[Your Firm]";
  const date = new Date().toLocaleDateString("en-US",{month:"long",year:"numeric"});

  const content = {
    "Situation Overview":     ["- Executive summary and deal rationale","- Market context and timing","- Headline terms"],
    "Strategic Rationale":    ["- Core investment thesis","- Key themes: "+(args.key_themes||"[analyst to complete]"),"- Synergy framework","- Strategic alternatives considered"],
    "Target Overview":        [`- Business description: ${args.target||"[target]"}`,"- Operating model","- Management team","- Competitive positioning"],
    "Market Analysis":        [`- ${sector} market size and dynamics`,"- Competitive landscape","- Regulatory environment"],
    "Valuation Analysis":     ["- Trading comps","- Precedent transactions","- DCF","- Football field","- Premium analysis"],
    "Transaction Structure":  ["- Deal mechanics and consideration mix","- Key conditions and approvals"],
    "Financing Overview":     ["- Sources and uses","- Pro forma capitalization","- Credit metrics"],
    "Pro Forma Impact":       ["- Accretion / dilution","- Pro forma income statement","- Synergy schedule"],
    "Process & Timeline":     ["- Process steps","- Transaction timeline","- Key workstreams"],
    "Management Considerations": ["- Retention and incentive structure","- Equity rollover"],
    "Risk Factors":           ["- Transaction, regulatory, integration, and market risks"],
    "Appendix":               ["- Detailed model","- Additional comps","- Biographies","- Disclaimer"],
  };

  return [
    `${skills.pitchDeck}\n`,
    `---\n## Output\n`,
    `# ${deal_type} Pitch — ${client}`,
    `**${firm}**  |  **Sector:** ${sector}${args.deal_size ? `  |  **~$${Math.round(args.deal_size).toLocaleString()}M**` : ""}`,
    `*${date}*\n---`,
    "## Table of Contents\n",
    sections.map((s,i) => `${i+1}. ${s}`).join("\n"),
    "\n---",
    sections.map((s,i) => [`\n## ${i+1}. ${s}`, ...(content[s]||["[Analyst to complete]"])].join("\n")).join("\n"),
    "\n---",
    `*Confidential — ${firm} — For discussion purposes only. Not for distribution.*`,
  ].join("\n");
}

function handleMergerAD(args) {
  const acq = args.acquirer;
  const tgt = args.target;
  const ds  = args.deal_structure || {};

  const cashPct   = ds.cash_pct       ?? 0.5;
  const synergies = ds.synergies      ?? 0;
  const synRamp   = ds.synergy_ramp   ?? 2;
  const finRate   = ds.financing_rate ?? 0.06;
  const tax       = ds.tax_rate       ?? 0.25;

  const dealValue   = tgt.offer_price * tgt.shares_out;
  const cashPortion = dealValue * cashPct;
  const stockPortion= dealValue * (1 - cashPct);
  const acqPrice    = acq.market_cap ? acq.market_cap / acq.shares_out : 0;
  const newShares   = acqPrice ? stockPortion / acqPrice : 0;
  const totalShares = acq.shares_out + newShares;
  const interest    = cashPortion * finRate * (1 - tax);
  const synYr1      = synergies * (1 / synRamp) * (1 - tax);
  const pfNI        = acq.net_income + tgt.net_income + synYr1 - interest;
  const pfEPS       = totalShares ? pfNI / totalShares : 0;
  const impact      = acq.eps ? ((pfEPS / acq.eps - 1) * 100).toFixed(1) : "N/A";
  const accretive   = pfEPS > acq.eps;
  const premium     = tgt.current_price ? ((tgt.offer_price / tgt.current_price - 1) * 100).toFixed(1) : null;

  return [
    `${skills.mergerAccretionDilution}\n`,
    `---\n## Output\n`,
    `## Merger A/D Analysis — ${acq.name} / ${tgt.name}`,
    `*${now()}*\n`,
    "### Transaction Overview",`| | |`,`|---|---|`,
    `| Offer Price | $${tgt.offer_price.toFixed(2)} |`,
    `| Deal Value | $${Math.round(dealValue).toLocaleString()}M |`,
    `| Cash | $${Math.round(cashPortion).toLocaleString()}M (${(cashPct*100).toFixed(0)}%) |`,
    `| Stock | $${Math.round(stockPortion).toLocaleString()}M (${((1-cashPct)*100).toFixed(0)}%) |`,
    premium ? `| Premium | ${premium > 0 ? "+" : ""}${premium}% |` : "",
    "",
    "### EPS Impact",
    "| | Standalone | Pro Forma |","|---|---|---|",
    `| Net Income ($M) | $${Math.round(acq.net_income).toLocaleString()} | $${Math.round(pfNI).toLocaleString()} |`,
    `| Diluted Shares (M) | ${acq.shares_out.toFixed(1)} | ${totalShares.toFixed(1)} |`,
    `| **EPS ($)** | **$${acq.eps.toFixed(2)}** | **$${pfEPS.toFixed(2)}** |`,
    `| **EPS Impact** | | **${accretive?"✅ Accretive":"❌ Dilutive"} ${impact > 0 ? "+" : ""}${impact}%** |`,
    "",
    "> ⚠️ Excludes purchase accounting, intangible amortization, transaction fees, and integration costs.",
  ].filter(l => l !== "").join("\n");
}

function handleIcMemo(args) {
  const { deal_name, deal_type, target_company } = args;
  return [
    `${skills.icMemo}\n`,
    `---\n## Output\n`,
    `# Investment Committee Memorandum`,
    `**Deal:** ${deal_name}  |  **Date:** ${args.committee_date||now()}  |  **Lead:** ${args.deal_lead||"[Deal Lead]"}`,
    `**Type:** ${deal_type}  |  **Sector:** ${args.sector||"—"}`,
    "\n---\n## I. Executive Summary",
    `Seeking IC approval to proceed with a **${deal_type}** in **${target_company}**`+(args.deal_size?` for approximately **$${Math.round(args.deal_size).toLocaleString()}M**`:"")+"."+
    (args.entry_multiple ? `\n**Entry:** ${args.entry_multiple.toFixed(1)}x EV/EBITDA` : "")+
    (args.target_irr     ? `  |  **Target IRR:** ${(args.target_irr*100).toFixed(0)}%` : "")+
    (args.hold_period    ? `  |  **Hold:** ${args.hold_period} years` : ""),
    "\n---\n## II. Investment Thesis", args.thesis||"[Analyst to complete]",
    "\n---\n## III. Company Overview",
    `**Company:** ${target_company}`,
    "- Business description: [Analyst to complete]",
    "- Revenue: $[X]M | EBITDA: $[X]M",
    "\n---\n## IV. Market Analysis",
    "- TAM: $[X]B | Growth: [X]% CAGR",
    "- Competitive dynamics: [Analyst to complete]",
    "\n---\n## V. Financial Overview",
    "| Metric | LTM | Y1E | Y2E | Y3E |","|---|---|---|---|---|",
    "| Revenue ($M) | | | | |","| EBITDA ($M) | | | | |","| FCF ($M) | | | | |",
    "\n---\n## VI. Valuation & Returns",
    "| | Low | Base | High |","|---|---|---|---|",
    "| IRR | | | |","| MOIC | | | |",
    "\n---\n## VII. Key Risks",
    "| Risk | Severity | Mitigant |","|---|---|---|",
    "| [Risk 1] | High / Med / Low | [Mitigant] |",
    args.key_risks ? `\n${args.key_risks}` : "",
    "\n---\n## VIII. Recommendation",
    `We **recommend approval** of the ${deal_type} in ${target_company}, subject to satisfactory completion of due diligence.`,
    "\n---\n*Confidential — IC use only. AI-assisted draft. All figures must be independently verified.*",
  ].filter(l => l != null).join("\n");
}

function handleWacc(args) {
  const ke   = args.risk_free_rate + args.beta * (args.equity_risk_premium ?? 0.055) + (args.size_premium ?? 0);
  const kdAt = args.cost_of_debt * (1 - (args.tax_rate ?? 0.25));
  const wacc = ke * args.equity_weight + kdAt * args.debt_weight;

  return [
    `${skills.waccCalculator}\n`,
    `---\n## Output\n`,
    `## WACC — ${args.company}`,`*${now()}*\n`,
    "### Cost of Equity (CAPM)",`| Component | Value |`,`|---|---|`,
    `| Risk-Free Rate | ${(args.risk_free_rate*100).toFixed(2)}% |`,
    `| Beta | ${args.beta.toFixed(2)}x |`,
    `| ERP | ${((args.equity_risk_premium??0.055)*100).toFixed(2)}% |`,
    `| Size Premium | ${((args.size_premium??0)*100).toFixed(2)}% |`,
    `| **Cost of Equity (Ke)** | **${(ke*100).toFixed(2)}%** |`,
    "","### Cost of Debt",`| Component | Value |`,`|---|---|`,
    `| Pre-Tax Kd | ${(args.cost_of_debt*100).toFixed(2)}% |`,
    `| **After-Tax Kd** | **${(kdAt*100).toFixed(2)}%** |`,
    "","### WACC",
    "| Component | Weight | Cost | Contribution |","|---|---|---|---|",
    `| Equity | ${(args.equity_weight*100).toFixed(0)}% | ${(ke*100).toFixed(2)}% | ${(ke*args.equity_weight*100).toFixed(2)}% |`,
    `| Debt | ${(args.debt_weight*100).toFixed(0)}% | ${(kdAt*100).toFixed(2)}% | ${(kdAt*args.debt_weight*100).toFixed(2)}% |`,
    `| **WACC** | **100%** | | **${(wacc*100).toFixed(2)}%** |`,
  ].join("\n");
}

function handleFootballField(args) {
  const { company, shares_out: shr, net_debt: nd, methodologies: methods } = args;
  const price  = args.current_price || 0;
  const ev2ps  = ev => shr ? (ev - nd) / shr : 0;

  return [
    `${skills.footballField}\n`,
    `---\n## Output\n`,
    `## Football Field Valuation — ${company}`,
    `*${now()}  |  Shares: ${shr.toLocaleString()}M  |  Net Debt: $${Math.round(nd).toLocaleString()}M*\n`,
    "| Methodology | EV Low ($M) | EV High ($M) | Price Low | Price High | Notes |",
    "|---|---|---|---|---|---|",
    ...methods.map(m =>
      `| ${m.method} | $${Math.round(m.ev_low).toLocaleString()} | $${Math.round(m.ev_high).toLocaleString()} | $${ev2ps(m.ev_low).toFixed(2)} | $${ev2ps(m.ev_high).toFixed(2)} | ${m.notes||""} |`
    ),
    `| **Overall Range** | | | **$${Math.min(...methods.map(m=>ev2ps(m.ev_low))).toFixed(2)}** | **$${Math.max(...methods.map(m=>ev2ps(m.ev_high))).toFixed(2)}** | |`,
    price ? `\n**Current Market Price:** $${price.toFixed(2)}` : "",
  ].filter(l => l !== "").join("\n");
}

function handleListTools() {
  return `## Finance MCP — Tool Directory

### Competitive Intelligence
| Tool | Description |
|---|---|
| \`competitive_analysis\` | Market structure, moats, growth quality, disruption risk, whitespace |

### Equity Research
| Tool | Slash | Description |
|---|---|---|
| \`comps_table\` | /comps | Trading comps with mean/median benchmarks |
| \`dcf_model\` | /dcf | 5-year DCF + WACC × terminal growth sensitivity |
| \`earnings_snapshot\` | /earnings | Beat/miss analysis + guidance + investor questions |
| \`one_pager\` | /one-pager | Company tearsheet / profile |

### Investment Banking
| Tool | Slash | Description |
|---|---|---|
| \`pitch_deck_outline\` | /pitch | Full pitch scaffold (M&A, IPO, Debt, Restructuring) |
| \`merger_accretion_dilution\` | /merger-ad | EPS accretion/dilution analysis |
| \`lbo_model\` | /lbo | IRR / MOIC returns matrix across exit multiples |
| \`ic_memo_template\` | /ic-memo | Investment Committee memo template |

### Utilities
| Tool | Description |
|---|---|
| \`wacc_calculator\` | WACC from CAPM + after-tax cost of debt |
| \`football_field\` | Valuation range across methodologies (fairness opinions, board decks) |
| \`list_tools\` | This listing |`;
}

// ═════════════════════════════════════════════════════════════════════════════
// REQUEST HANDLERS
// ═════════════════════════════════════════════════════════════════════════════

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  const dispatch = {
    competitive_analysis:       handleCompetitiveAnalysis,
    comps_table:                handleCompsTable,
    dcf_model:                  handleDcf,
    lbo_model:                  handleLbo,
    earnings_snapshot:          handleEarnings,
    one_pager:                  handleOnePager,
    pitch_deck_outline:         handlePitch,
    merger_accretion_dilution:  handleMergerAD,
    ic_memo_template:           handleIcMemo,
    wacc_calculator:            handleWacc,
    football_field:             handleFootballField,
    list_tools:                 handleListTools,
  };
  const handler = dispatch[name];
  if (!handler) throw new Error(`Unknown tool: ${name}`);
  try {
    return { content: [{ type: "text", text: handler(args || {}) }] };
  } catch (err) {
    return { content: [{ type: "text", text: `❌ Error in ${name}: ${err.message}` }] };
  }
});

// ═════════════════════════════════════════════════════════════════════════════
// START
// ═════════════════════════════════════════════════════════════════════════════

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("Finance MCP server running — 11 tools, 11 skills loaded.");
