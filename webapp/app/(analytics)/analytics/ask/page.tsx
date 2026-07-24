// Ask Scout (Tier-2) full page + the tier ladder + Connect-your-own-Claude (Tier-3).
// Build-time server component: reads the committed ask corpus (no /api, no client
// fetch, no live data) and hands it to the client router <AskBox>. The MCP config
// is verbatim from docs/MCP_QUICKSTART.md. DESIGN_ANALYTICS Sec. 6-7 + mockups/ask.html.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { AskBox, type AskEntry, type AskTour } from "@/components/analytics/AskBox";

export const metadata: Metadata = {
  title: "Ask Scout",
  description:
    "Ask about the players, teams, and metrics Scout has already studied across four sports. Scout answers only from precomputed, receipt-cited data -- and says NO_DATA plainly when it has none.",
};

// Clone-safe, repo-relative read (mirrors lib/showcase.server.ts). Fresh clones
// that lack the staged corpus fall back to an empty router rather than hard-fail.
function loadEntries(): AskEntry[] {
  try {
    const raw = readFileSync(join(process.cwd(), "public", "data", "ask", "corpus.json"), "utf-8");
    const parsed = JSON.parse(raw) as { entries?: AskEntry[] };
    return Array.isArray(parsed.entries) ? parsed.entries : [];
  } catch {
    return [];
  }
}

// Suggested tours by bucket (NIGHT_PLAN: "suggested tours by bucket"). Data-driven:
// two representative questions per known bucket, order preserved from the corpus.
const BUCKETS: Array<{ key: string; label: string }> = [
  { key: "calibration-market", label: "Calibration & the market" },
  { key: "players-teams", label: "Players & teams" },
  { key: "system-honesty", label: "How the system works" },
  { key: "no_data_honest", label: "Where Scout says no" },
];
function buildTours(entries: AskEntry[]): AskTour[] {
  return BUCKETS.map((b) => ({
    label: b.label,
    questions: entries
      .filter((e) => e.bucket === b.key)
      .slice(0, 2)
      .map((e) => e.q),
  })).filter((t) => t.questions.length > 0);
}

const MCP_CONFIG = `{
  "mcpServers": {
    "courtvision": {
      "command": "python",
      "args": ["-m", "scripts.platformkit.mcp_server.server"],
      "env": { "PYTHONPATH": "." }
    }
  }
}

# 9 tools: ask, scouting_report, matchup_preview, comparables,
# win_probability, injury_report, analytics_receipts, run_burst,
# system_health`;

const h1S: CSSProperties = {
  fontFamily: "var(--font-display)",
  fontWeight: 500,
  fontSize: "clamp(2.2rem,5vw,3.2rem)",
  letterSpacing: "-.02em",
  color: "var(--ink)",
  margin: "40px 0 8px",
};
const lede: CSSProperties = {
  color: "var(--ink-2)",
  fontSize: 18,
  lineHeight: 1.6,
  maxWidth: "52ch",
  marginBottom: 28,
};
const tierCard = (active: boolean): CSSProperties => ({
  background: "var(--paper-raised)",
  border: `1px solid ${active ? "var(--accent)" : "var(--rule)"}`,
  borderRadius: "var(--radius-card, 10px)",
  boxShadow: active ? "var(--shadow-raise)" : "var(--shadow-card)",
  padding: 16,
});
const codeBlock: CSSProperties = {
  background: "#241f1a",
  color: "#e9e0d2",
  // A token border separates the block from the panel in BOTH themes -- its dark
  // #241f1a ground is nearly identical to --paper-raised (#24201C) in dark mode, so
  // without this it lost its boundary and read as loose floating text.
  border: "1px solid var(--rule-strong)",
  borderRadius: "var(--radius-card, 10px)",
  padding: 16,
  fontFamily: "var(--font-mono)",
  fontSize: 12.5,
  lineHeight: 1.6,
  // pre-wrap (not pre) so the longest line ("args": [...server"]) wraps into view on
  // a narrow phone instead of scrolling off with no edge-fade cue. Soft-wrap only --
  // the copied text keeps its real newlines/spaces, so the config stays valid JSON.
  overflowX: "auto",
  margin: 0,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const TIERS = [
  {
    n: "1",
    t: "Scout notes",
    d: "Precomputed, cited notes on all 54 analytics modules and 182 marquee entity cards. The other 1,367 entity cards carry their measured numbers and receipts, without a written note. Zero runtime compute.",
    active: false,
  },
  {
    n: "2",
    t: "Ask Scout",
    d: "This box. A client-side router over the committed corpus -- real answers, honest NO_DATA, no network.",
    active: true,
  },
  {
    n: "3",
    t: "Your own Claude",
    d: "The full AI, live, running in your Claude via our open MCP -- ask anything the data supports.",
    active: false,
  },
];

export default function AskPage() {
  const entries = loadEntries();
  const tours = buildTours(entries);

  return (
    <div className="wrap" style={{ maxWidth: 860, paddingBottom: 24 }}>
      <p className="overline" style={{ marginTop: 40 }}>
        Scout &middot; Tier 2
      </p>
      <h1 style={h1S}>Ask Scout</h1>
      <p style={lede}>
        Ask about the players, teams, and metrics Scout has already studied across four
        sports. Scout answers only from precomputed, receipt-cited data &mdash; and says
        NO_DATA plainly when it has none.
      </p>

      <AskBox entries={entries} tours={tours} />

      {/* tier ladder */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))",
          gap: 14,
          margin: "40px 0",
        }}
      >
        {TIERS.map((t) => (
          <div key={t.n} style={tierCard(t.active)}>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "1.4rem", color: "var(--accent)" }}>
              {t.n}
            </div>
            <div style={{ fontWeight: 600, fontSize: 15, color: "var(--ink)", margin: "4px 0 6px" }}>{t.t}</div>
            <div style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.5 }}>{t.d}</div>
          </div>
        ))}
      </div>

      {/* tier 3 -- connect your own Claude */}
      <section
        aria-labelledby="connect-h"
        style={{
          background: "var(--paper-raised)",
          border: "1px solid var(--rule-strong)",
          borderRadius: "var(--radius-panel, 14px)",
          boxShadow: "var(--shadow-raise)",
          overflow: "hidden",
          marginBottom: 48,
        }}
      >
        <div style={{ height: 4, background: "var(--signal)" }} />
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))",
            gap: 28,
            padding: 26,
          }}
        >
          <div>
            <p className="overline" style={{ color: "var(--signal-ink)" }}>
              Tier 3 &middot; Full AI
            </p>
            <h2
              id="connect-h"
              style={{ fontFamily: "var(--font-display)", fontWeight: 500, fontSize: 24, color: "var(--ink)", margin: "6px 0 8px" }}
            >
              Go deeper &mdash; connect your own Claude
            </h2>
            <p style={{ fontSize: 14.5, color: "var(--ink-2)", lineHeight: 1.6 }}>
              Point Claude at the CourtVision MCP and ask anything the data supports --
              scouting reports, matchup previews, comparables, calibrated win
              probabilities. Nine typed tools resolve your question against the same
              artifacts this site cites.
            </p>
            <ol style={{ listStyle: "none", margin: "14px 0 0", padding: 0 }}>
              {[
                "Install the CourtVision MCP server in Claude.",
                "Add the connector config on the right.",
                "Ask in plain language -- 9 typed tools resolve it.",
              ].map((s, i) => (
                <li
                  key={i}
                  style={{
                    fontSize: 14.5,
                    color: "var(--ink-2)",
                    padding: "8px 0",
                    borderBottom: i < 2 ? "1px solid var(--rule)" : "none",
                  }}
                >
                  <span
                    aria-hidden
                    style={{
                      display: "inline-grid",
                      placeItems: "center",
                      width: 20,
                      height: 20,
                      borderRadius: "50%",
                      background: "var(--accent)",
                      color: "var(--accent-ink-on, #fff)",
                      fontSize: 12,
                      fontWeight: 700,
                      marginRight: 10,
                      verticalAlign: "middle",
                    }}
                  >
                    {i + 1}
                  </span>
                  {s}
                </li>
              ))}
            </ol>
            <p style={{ fontSize: 13, color: "var(--signal-ink)", fontWeight: 500, marginTop: 14, lineHeight: 1.5 }}>
              This runs inside YOUR Claude session using our open MCP server. We don't
              host an LLM &mdash; your questions never touch our servers.
            </p>
            <p style={{ fontSize: 14, marginTop: 12 }}>
              {/* /use-it lives in the terminal product (own theme, full reload) --
                  the up-right glyph + label mark this as a cross-product jump, not
                  an in-Reading-Room docs link. */}
              <Link href="/use-it" target="_blank" rel="noopener">Full MCP quickstart &amp; tool reference &mdash; opens in the terminal &#8599;</Link>
            </p>
          </div>
          <div>
            {/* ponytail: selectable <pre>, no copy button -- would need a client island
                for one clipboard call; the /use-it page carries the copyable setup. */}
            <pre style={codeBlock}>{MCP_CONFIG}</pre>
          </div>
        </div>
      </section>
    </div>
  );
}
