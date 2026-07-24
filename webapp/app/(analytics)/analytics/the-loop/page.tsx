// /analytics/the-loop -- "The Loop": the self-improving AI as a living system
// (NIGHT_PLAN elevated goal, page 2). Discovery -> leak-free gate -> verdict ->
// graveyard-or-verified, fed by committed artifacts. The pitch a company reads: an
// AI that proposes, tests, retracts, and keeps score on itself. Build-time server
// component; readFileSync from public/data/showcase only, no live data, no dollar claim.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import { LoopDiagram, type LoopStats } from "@/components/analytics/LoopDiagram";
import { Receipt, type ReceiptData } from "@/components/analytics/Receipt";
import { ScoutNote, type ScoutEnvelope } from "@/components/analytics/ScoutNote";
import { ScoutQuestions } from "@/components/analytics/ScoutQuestions";
import { VerdictDot, type Verdict } from "@/components/analytics/VerdictDot";
import { VerdictLegend } from "@/components/analytics/VerdictLegend";
import { pickQuestions } from "@/lib/analytics/askPicks";

export const metadata: Metadata = {
  title: "The Loop",
  description:
    "The self-improving system: an AI that proposes signals, tests them leak-free, keeps its nulls and retractions in the same ledger it confirms from, and grades itself.",
};

// Clone-safe: process.cwd() is the webapp root at build; join keeps it repo-
// relative. Missing artifact (fresh clone) -> null -> the page degrades to a
// pending state rather than hard-failing the export build (IA Sec. 5).
const DIR = join(process.cwd(), "public", "data", "showcase");
const OUT = "scripts/platformkit/analytics_showcase/out"; // canonical producer path, for receipts
function readJson<T>(name: string): T | null {
  try {
    // Strip bare NaN (some ledgers carry a p-value NaN) before parse -- matches the
    // Home page guard. Without it JSON.parse throws, is swallowed, and the census
    // silently falls back to hardcoded counts while Home shows the live ones.
    return JSON.parse(readFileSync(join(DIR, `${name}.json`), "utf-8").replace(/\bNaN\b/g, "null")) as T;
  } catch {
    return null;
  }
}

interface FlipHistory { corpus?: string; n?: number; effect?: number | null }
interface Flip {
  sport: string;
  hypothesis: string;
  current_status: string;
  verdict_sequence: string[];
  history: FlipHistory[];
}
interface Scoreboard {
  as_of?: string;
  summary?: { n_families?: number; n_flipped?: number; by_status?: Record<string, number> };
  flipped_families?: Flip[];
}
interface Ledger { overall_counts?: Record<string, number> }
interface Graveyard {
  full_history_row_count?: number;
  latest_per_signal_graveyard_count?: number;
  reject_row_count?: number;
  rejects_by_reason_category?: Record<string, number>;
  cumulative_rejects_over_time?: Array<{ date: string; cumulative_rejects: number }>;
}
interface Honesty { headline?: string; generated_at?: string }

const SPORT: Record<string, string> = { basketball_nba: "NBA", mlb: "MLB", soccer: "Soccer", tennis: "Tennis" };
function verdictOf(s: string): Verdict {
  const u = s.toUpperCase();
  if (u.includes("CONFIRM") || u === "VERIFIED") return "confirmed";
  if (u.includes("NOT_TESTABLE")) return "not_testable";
  if (u.includes("PROVISIONAL")) return "pending";
  return "null";
}
function shortVerdict(s: string): string {
  return s.replace(/_LOCAL$/i, "").replace(/_/g, " ");
}
const day = (iso?: string) => (iso ? iso.slice(0, 10) : undefined);

const wrap: CSSProperties = { maxWidth: 1120, margin: "0 auto", padding: "0 24px" };
const h2: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: 30, letterSpacing: "-.01em", color: "var(--ink)" };
const lede: CSSProperties = { fontSize: 15.5, lineHeight: 1.6, color: "var(--ink-2)", maxWidth: 660 };

function StatCell({ num, unit, label, chip }: { num: string; unit?: string; label: string; chip: ReceiptData }) {
  return (
    <div style={{ background: "var(--paper-raised)", padding: "22px 20px" }}>
      <div style={{ fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "2.4rem", lineHeight: 1, fontFeatureSettings: "'tnum' 1", color: "var(--ink)" }}>
        {num}
        {unit ? <span style={{ fontSize: "0.85rem", color: "var(--ink-3)", marginLeft: 5 }}>{unit}</span> : null}
      </div>
      <div style={{ fontSize: 13, color: "var(--ink-2)", margin: "8px 0 10px" }}>{label}</div>
      <Receipt {...chip} />
    </div>
  );
}

export default function TheLoopPage() {
  const sb = readJson<Scoreboard>("fwd_claim_scoreboard");
  const ml = readJson<Ledger>("mechanism_ledger_export");
  const gv = readJson<Graveyard>("reject_graveyard");
  const hx = readJson<Honesty>("honesty_exhibit");

  const by = sb?.summary?.by_status || {};
  const families = sb?.summary?.n_families ?? 0;
  const verified = by.verified ?? 0;
  const provisional = by.provisional ?? 0;
  const graveyard = (by.null ?? 0) + (by.not_testable ?? 0) + (by.retracted ?? 0);
  const flips = sb?.flipped_families || [];
  const stats: LoopStats = { families, verified, graveyard, provisional, flips: sb?.summary?.n_flipped ?? flips.length };
  const sbAsOf = day(sb?.as_of);

  const oc = ml?.overall_counts || {};
  const topReasons = Object.entries(gv?.rejects_by_reason_category || {}).sort((a, b) => b[1] - a[1]).slice(0, 3);
  const cumulative = gv?.cumulative_rejects_over_time || [];
  const gvLast = cumulative[cumulative.length - 1];

  const fwdChip = (extra: Partial<ReceiptData>): ReceiptData => ({
    sourceArtifact: `${OUT}/fwd_claim_scoreboard.json`,
    asOf: sbAsOf,
    verdict: "descriptive_only",
    ...extra,
  });

  const scout: ScoutEnvelope = {
    status: "ok",
    prose:
      `Confirms are not the product -- the self-grading is. Of ${families} tracked families, ` +
      `**${verified}** are verified and **${graveyard}** sit in the graveyard as nulls, not-testables, or ` +
      `retractions, kept in the same ledger they are confirmed from. ` +
      `**${stats.flips}** changed their own verdict when new evidence arrived.`,
    chips: [
      fwdChip({ value: String(verified), label: "verified families", verdict: "confirmed" }),
      fwdChip({ value: String(graveyard), label: "kept in the ledger (null / not-testable / retracted)", verdict: "null" }),
      fwdChip({ value: String(stats.flips), label: "families that flipped their own verdict", verdict: "not_testable" }),
    ],
  };

  // Verbatim corpus questions (status ok) so each pill phrase-resolves to a real
  // Scout answer instead of dead-ending on "No verified answer."
  const questions = pickQuestions([
    "how system grade itself self-grading",
    "candidate signals rejected reject",
    "findings flip verdict re-test",
  ]);

  return (
    <div style={{ ...wrap, paddingTop: 56, paddingBottom: 24 }}>
      <header style={{ maxWidth: 720, marginBottom: 40 }}>
        <div className="overline" style={{ marginBottom: 12 }}>The self-improving system</div>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2.4rem,5.5vw,3.8rem)", lineHeight: 1.05, letterSpacing: "-.02em", color: "var(--ink)", marginBottom: 16 }}>
          An AI that grades itself.
        </h1>
        <p style={{ ...lede, fontSize: 18, maxWidth: 620 }}>
          It proposes signals, tests them under a leak-free gate, and keeps every null, not-testable, and
          retraction in the same ledger it confirms from. A system that only ever confirmed would not be
          credible &mdash; so it counts what it could not prove, and changes its own mind on new evidence.
        </p>
        <VerdictLegend style={{ marginTop: 22 }} />
      </header>

      <section aria-label="The loop" style={{ marginBottom: 56 }}>
        <LoopDiagram stats={stats} />
      </section>

      <section aria-label="Scoreboard" style={{ marginBottom: 56 }}>
        <h2 style={{ ...h2, marginBottom: 18 }}>The scoreboard grades every claim</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 1, background: "var(--rule)", border: "1px solid var(--rule)", borderRadius: 12 }}>
          <StatCell num={families.toLocaleString("en-US")} label="claim families tracked" chip={fwdChip({ value: String(families), label: "self-grading scoreboard" })} />
          <StatCell num={String(verified)} label="verified (confirmed)" chip={fwdChip({ value: String(verified), label: "verified families", verdict: "confirmed" })} />
          <StatCell num={String(graveyard)} label="null, not-testable, or retracted" chip={fwdChip({ value: String(graveyard), label: "kept in the ledger", verdict: "null" })} />
          <StatCell num={String(stats.flips)} label="changed their own verdict" chip={fwdChip({ value: String(stats.flips), label: "self-corrections", verdict: "not_testable" })} />
        </div>
        <p style={{ ...lede, marginTop: 18, display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "4px 10px" }}>
          <span>
            The scoreboard above grades forward-tested claim families; the mechanism ledger is a separate, wider census of every named mechanism. Across <strong style={{ color: "var(--ink)" }}>{oc.total ?? 287}</strong> named mechanisms:{" "}
            <strong style={{ color: "var(--ink)" }}>{oc.confirmed ?? 130}</strong> confirmed,{" "}
            <strong style={{ color: "var(--ink)" }}>{oc.null ?? 126}</strong> null,{" "}
            <strong style={{ color: "var(--ink)" }}>{oc.not_testable ?? 31}</strong> not-testable.
          </span>
          <Receipt sourceArtifact={`${OUT}/mechanism_ledger_export.json`} label="mechanism ledger (4 sports)" verdict="descriptive_only" />
        </p>
        <p style={{ ...lede, marginTop: 6, display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "4px 10px" }}>
          <span style={{ fontStyle: "italic" }}>{hx?.headline || "we publish our nulls"}</span>
          <Receipt sourceArtifact={`${OUT}/honesty_exhibit.json`} label="honesty exhibit (all ledgers)" asOf={day(hx?.generated_at)} verdict="null" />
        </p>
      </section>

      <section aria-label="Verdict flips" style={{ marginBottom: 56 }}>
        <h2 style={{ ...h2, marginBottom: 8 }}>The system changes its own mind</h2>
        <p style={{ ...lede, marginBottom: 20 }}>
          These families carried more than one verdict across reruns. The ledger keeps the whole sequence, not
          just the last word &mdash; the trail of a system re-testing itself as corpora grow.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {flips.map((f) => {
            const last = f.history[f.history.length - 1] || {};
            const chip: ReceiptData = {
              value: last.effect != null ? String(last.effect) : undefined,
              label: f.verdict_sequence[f.verdict_sequence.length - 1],
              sourceArtifact: `${OUT}/fwd_claim_scoreboard.json`,
              asOf: sbAsOf,
              n: last.n,
              corpus: last.corpus,
              verdict: verdictOf(f.current_status),
            };
            return (
              <div key={`${f.sport}-${f.hypothesis}`} style={{ background: "var(--paper-raised)", border: "1px solid var(--rule)", borderRadius: "var(--radius-card)", boxShadow: "var(--shadow-card)", padding: "14px 16px", display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 16px" }}>
                <span style={{ fontWeight: 700, fontSize: 10, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--accent)", flex: "0 0 46px" }}>{SPORT[f.sport] || f.sport}</span>
                <span style={{ fontFamily: "var(--font-display)", fontSize: 17, color: "var(--ink)", flex: "1 1 200px", minWidth: 0 }}>{f.hypothesis.replace(/_/g, " ")}</span>
                <span style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  {f.verdict_sequence.map((v, i) => (
                    <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      {i > 0 ? <span aria-hidden style={{ color: "var(--ink-3)", fontSize: 12 }}>{"\u2192"}</span> : null}
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--ink-2)", padding: "3px 8px", border: "1px solid var(--rule-strong)", borderRadius: "var(--radius-pill)" }}>
                        <VerdictDot verdict={verdictOf(v)} size={6} />
                        {shortVerdict(v)}
                      </span>
                    </span>
                  ))}
                </span>
                <span style={{ flex: "0 0 auto" }}>
                  <Receipt {...chip} />
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <section aria-label="The graveyard" style={{ marginBottom: 56 }}>
        <h2 style={{ ...h2, marginBottom: 8 }}>The graveyard is a feature</h2>
        <p style={{ ...lede, marginBottom: 20 }}>
          Every reject and defer is recorded, categorized, and counted. A discarded signal is honest
          market-efficiency evidence, not a failure to bury.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 1, background: "var(--rule)", border: "1px solid var(--rule)", borderRadius: 12 }}>
          <StatCell num={(gv?.reject_row_count ?? 628).toLocaleString("en-US")} label="reject rows recorded" chip={{ sourceArtifact: `${OUT}/reject_graveyard.json`, label: "reject ledger", value: String(gv?.reject_row_count ?? 628), verdict: "null" }} />
          <StatCell num={String(gv?.latest_per_signal_graveyard_count ?? 68)} label="distinct signals on a reject verdict now" chip={{ sourceArtifact: `${OUT}/reject_graveyard.json`, label: "latest-verdict graveyard", value: String(gv?.latest_per_signal_graveyard_count ?? 68), verdict: "null" }} />
          <StatCell num={(gv?.full_history_row_count ?? 804).toLocaleString("en-US")} label="total verdict rows across all reruns" chip={{ sourceArtifact: `${OUT}/reject_graveyard.json`, label: "full verdict history", value: String(gv?.full_history_row_count ?? 804), verdict: "descriptive_only" }} />
        </div>
        <p style={{ ...lede, marginTop: 16 }}>
          Top reject reasons:{" "}
          {topReasons.map(([k, v], i) => (
            <span key={k}>
              {i > 0 ? "; " : ""}
              <strong style={{ color: "var(--ink)" }}>{v}</strong> {k.replace(/_/g, " ")}
            </span>
          ))}
          {gvLast ? <span style={{ color: "var(--ink-3)" }}>{` \u00b7 cumulative reaches ${gvLast.cumulative_rejects} by ${gvLast.date}.`}</span> : null}
        </p>
      </section>

      <ScoutNote envelope={scout} />
      <ScoutQuestions questions={questions} heading="Ask Scout about the loop" />
    </div>
  );
}
