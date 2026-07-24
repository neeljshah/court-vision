// About -- what CourtVision Analytics is, the three Scout tiers, MCP pointer,
// builder credit, methodology pointer, logo treatment. Pure static prose: no
// staged JSON needed, so no data/ read at build (IA Sec 5 fresh-clone rule is
// automatically satisfied -- nothing here can be missing on a clone).
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About",
  description:
    "What CourtVision Analytics is, the three Scout AI tiers, and who built it.",
};

const section: CSSProperties = { padding: "56px 0", borderTop: "1px solid var(--rule)" };
const h2: CSSProperties = {
  fontFamily: "var(--font-display)",
  fontWeight: 500,
  fontSize: 30,
  letterSpacing: "-.01em",
  color: "var(--ink)",
  marginBottom: 16,
};
const lede: CSSProperties = { fontSize: 16.5, lineHeight: 1.7, color: "var(--ink-2)", maxWidth: "62ch" };
const card: CSSProperties = {
  background: "var(--paper-raised)",
  border: "1px solid var(--rule)",
  borderRadius: "var(--radius-card)",
  boxShadow: "var(--shadow-card)",
  padding: "20px 22px",
};

const TIERS = [
  {
    n: "1",
    name: "Scout notes",
    where: "on every module and entity page",
    body:
      "A precomputed, receipt-cited note read from a committed insight file. No runtime compute -- if there is no verified read, it says so (\"Scout has no verified read on this yet\") instead of guessing.",
  },
  {
    n: "2",
    name: "Ask Scout",
    where: "the /analytics/ask page + a box on Home",
    body:
      "A client-side router: your question is keyword/entity-matched against a precomputed answer corpus. No LLM, no network call. Honest NO_DATA fallback when nothing matches.",
  },
  {
    n: "3",
    name: "Connect your own Claude",
    where: "MCP, prominent on /analytics/ask",
    body:
      "The full AI tier runs inside YOUR Claude session via the open courtvision MCP server (9 tools: ask, scouting_report, comparables, matchup_preview, win_probability, injury_report, analytics_receipts, run_burst, system_health). We don't host an LLM -- your questions never touch our servers.",
  },
];

export default function AboutPage() {
  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 24 }}>
      <p className="overline">About</p>
      <h1 style={{ ...h2, fontSize: 40, marginTop: 8 }}>What CourtVision Analytics is</h1>
      <p style={lede}>
        CourtVision is an AI-native sports intelligence platform: computer-vision tracking,
        official box-score APIs, and a library of trained signals feed a possession-level Monte
        Carlo simulator, producing calibrated forecasts across NBA, MLB, soccer, and tennis. This
        site is the honest read-out of that pipeline -- every number on it carries the artifact
        that produced it. The product is a <em>calibrated predictor</em>, not a betting-edge
        service; an honest null result is a success here, not a failure. Full discipline and
        proof harness: <Link href="/analytics/the-loop">What verified means &rarr;</Link>
      </p>

      <section style={section} aria-labelledby="tiers-h">
        <h2 id="tiers-h" style={h2}>The three Scout tiers</h2>
        <p style={{ ...lede, marginBottom: 24 }}>
          &ldquo;Scout&rdquo; is CourtVision&rsquo;s AI presence, shown as a ladder from
          precomputed to fully live. Each tier is labeled for exactly what it can and cannot do.
        </p>
        <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))" }}>
          {TIERS.map((t) => (
            <div key={t.n} style={card}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 6 }}>
                <span className="mono" style={{ fontSize: 12, color: "var(--signal-ink)" }}>Tier {t.n}</span>
                <span style={{ fontFamily: "var(--font-display)", fontSize: 18, color: "var(--ink)" }}>{t.name}</span>
              </div>
              <p style={{ fontSize: 12.5, color: "var(--ink-3)", marginBottom: 10 }}>{t.where}</p>
              <p style={{ fontSize: 14.5, lineHeight: 1.6, color: "var(--ink-2)" }}>{t.body}</p>
            </div>
          ))}
        </div>
        <p style={{ ...lede, marginTop: 20, fontSize: 14.5 }}>
          Quickstart for tier 3 (clone, `pip install pandas numpy`, run the server -- stdlib-only
          at boot): <code className="mono">docs/MCP_QUICKSTART.md</code> in this repo, or go
          straight to <Link href="/analytics/ask">Ask Scout &rarr;</Link>
        </p>
      </section>

      <section style={section} aria-labelledby="mark-h">
        <h2 id="mark-h" style={h2}>The mark</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <span
            aria-hidden
            style={{
              width: 52, height: 52, borderRadius: "50%", display: "grid", placeItems: "center",
              background: "radial-gradient(circle at 35% 30%, #e9e4da, #b9b0a3 60%, #8f8578)",
              boxShadow: "inset 0 0 0 3px #ccc4b6", flex: "0 0 auto",
            }}
          >
            <span style={{ color: "var(--signal)", fontWeight: 800, fontSize: 24, lineHeight: 1, transform: "translateY(-2px)" }}>
              {"\u25B2"}
            </span>
          </span>
          <p style={{ ...lede, fontSize: 14.5 }}>
            A silver ring with an amber aperture arrow. The arrow alone is the Scout glyph --
            the favicon and the loading mark. The full lockup pairs it with{" "}
            <span style={{ fontFamily: "var(--font-display)" }}>CourtVision</span>{" "}
            in Fraunces and an <span className="overline" style={{ fontSize: 10 }}>ANALYTICS</span>{" "}
            overline in Libre Franklin. Amber is reserved for this mark and the Scout glyph only --
            it never doubles as a data color on a chart.
          </p>
        </div>
      </section>

      <section style={{ ...section, paddingBottom: 8 }} aria-labelledby="builder-h">
        <h2 id="builder-h" style={h2}>Built by</h2>
        <p style={lede}>
          <a href="https://neelshahportfolio.netlify.app" target="_blank" rel="noreferrer noopener">
            Neel Shah
          </a>{" "}
          -- solo human architect/director of an agentic build pipeline (Claude agents write,
          test, and ship or reject every signal on this site). Contact:{" "}
          <a href="mailto:neeljshah22@gmail.com">neeljshah22@gmail.com</a>.
        </p>
      </section>
    </div>
  );
}
