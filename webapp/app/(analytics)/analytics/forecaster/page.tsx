// The Forecaster -- the calibrated prediction engine as a story page (NIGHT_PLAN
// ELEVATED GOAL). Walk-forward proof, the in-game conditioning win as centerpiece,
// "what the model sees" state grid, cross-sport scoreboard, Scout questions footer.
// Build-time server component: reads staged public/data/showcase/forecaster/*.json;
// missing on a fresh clone -> the exhibit shows VALIDATION_PENDING, never fabricates.
// Numbers verbatim from committed artifacts; no edge/ROI language. ASCII only.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { CSSProperties } from "react";
import { Grid } from "@/components/analytics/charts/Grid";
import { Bars, type BarDatum } from "@/components/analytics/charts/Bars";
import { ScoutNote } from "@/components/analytics/ScoutNote";
import { ScoutQuestions } from "@/components/analytics/ScoutQuestions";
import { Receipt } from "@/components/analytics/Receipt";
import type { Verdict } from "@/components/analytics/VerdictDot";

export const metadata = { title: "The Forecaster" };

// staged-artifact reader (forecaster subdir; null on a fresh clone -> pending)
function fc<T>(name: string): T | null {
  try {
    return JSON.parse(readFileSync(join(process.cwd(), "public", "data", "showcase", "forecaster", name), "utf-8")) as T;
  } catch {
    return null;
  }
}
type Fold = { acc: number; brier: number; n_train: number; n_val: number; train_end_frac: number };
type WF = { acc_mean: number; acc_std: number; brier_mean: number; brier_std: number; n_features: number; seasons: string[]; folds: Fold[] };
type Bucket = { time_bucket: string; prob_bucket: string; source: string; n: number; calibration_error: number; sport: string };
type SCC = { sports: Record<string, { model_ece_n_weighted: number; market_ece_n_weighted: number; buckets: Bucket[] }>; ranked_worst_buckets: Bucket[] };
type Row = { sport: string; market: string; checkpoint: string; n: number; paired_delta_mean: number; paired_delta_95ci: [number, number]; verdict: string };
type Tr = { sport: string; from: { time: string; prob: string }; to: { time: string; prob: string }; winprob_delta: number; min_support_n: number };

const wf = fc<WF>("winprob_walk_forward_results.json");
const scc = fc<SCC>("state_conditioned_calibration.json");
const cs = fc<{ rows: Row[]; honest_note: string }>("cross_sport_scoreboard.json");
const why = fc<{ biggest_drops: Tr[]; biggest_gains: Tr[] }>("../why_attribution.json");

const f3 = (n: number) => n.toFixed(3);
const sgn = (n: number, d = 4) => `${n >= 0 ? "+" : ""}${n.toFixed(d)}`;
const SPORT: Record<string, string> = { nba: "NBA", mlb: "MLB", mlb_ingame: "MLB (in-game)", mlb_pregame: "MLB (pregame)", soccer_intl: "Soccer" };
const sName = (s: string) => SPORT[s] || s;
const tShort = (t: string) => t.split("(")[0];
const vtok = (v: string): Verdict => (v.startsWith("MODEL_SHARPER") ? "confirmed" : v.startsWith("MARKET_SHARPER") ? "not_testable" : "null");
const dotVar = (v: Verdict) => (v === "confirmed" ? "confirmed" : v === "not_testable" ? "not-testable" : "null");

// "what the model sees": pivot MLB model buckets into a time x prob-band grid
const TIMES = ["early(inn1-3)", "mid(inn4-6)", "late(inn7+)"];
const PROBS = ["0-.2", ".2-.4", ".4-.6", ".6-.8", ".8-1"];
const gridVals: (number | null)[][] = TIMES.map((t) =>
  PROBS.map((p) => scc?.sports.mlb?.buckets.find((x) => x.source === "model" && x.time_bucket === t && x.prob_bucket === p)?.calibration_error ?? null)
);
const backlog: BarDatum[] = (scc?.ranked_worst_buckets ?? []).slice(0, 6).map((b) => ({
  label: `${sName(b.sport)} ${tShort(b.time_bucket)} ${b.prob_bucket}`, value: b.calibration_error, sub: `n=${b.n}`, color: "var(--signal)",
}));
const trans: BarDatum[] = why
  ? [...why.biggest_drops.slice(0, 3), ...why.biggest_gains.slice(0, 3)].map((t) => ({
      label: `${sName(t.sport)} ${tShort(t.from.time)}->${tShort(t.to.time)}`, value: t.winprob_delta,
      sub: `${t.from.prob}->${t.to.prob}  n>=${t.min_support_n}`, color: "var(--accent)",
    }))
  : [];

// In-game three-arm decomposition -- verbatim from committed docs/INGAME_PROOF.md
// Sec. 2 + 2a. That doc is tracked, so the narrative renders on every clone; the
// live re-run prints VALIDATION_PENDING (hence the pending receipt).
const ARMS = [
  { sport: "NBA", stat: 0.209, score: 0.172, comb: 0.159, mech: "~73%", prior: "-0.014 (~27%)" },
  { sport: "MLB", stat: 0.241, score: 0.128, comb: 0.126, mech: "~99%", prior: "-0.001 (~1%)" },
];
const SCOUT_CHIPS: Parameters<typeof Receipt>[0][] = [
  { label: "CALIBRATION_OOS (VALIDATION_PENDING on fresh clone)", sourceArtifact: "docs/INGAME_PROOF.md", asOf: "2026-07-23", verdict: "pending" },
  { label: "BSS vs market -- null is the exhibit", sourceArtifact: "scripts/platformkit/analytics_showcase/out/brier_skill_scores.json", asOf: "2026-07-24", n: 78986, verdict: "null" },
  { label: "walk-forward, expanding window", sourceArtifact: "results/winprob_walk_forward_results.json", asOf: "2026-07-20", verdict: "confirmed" },
];
const SCOUT_PROSE =
  "Pregame, the forecaster **matches** the devigged close within noise and beats nothing. The one measured win is **in-game**: conditioning NBA win-probability on the realized state sharpens calibration to Brier **0.159** -- but most of that lift is the scoreboard itself, and the model's own prior adds only the last **~0.014**. Against the market's Brier, skill is **near or below zero** across sports; that null is the point, not a defect.";
const QUESTIONS = [
  "How well calibrated is the NBA in-game win probability model?",
  "Does the forecaster beat the market pregame?",
  "Where is the forecaster's calibration weakest?",
];

// styles
const sec: CSSProperties = { marginTop: 64 };
const eye: CSSProperties = { fontWeight: 700, fontSize: 11, letterSpacing: "0.13em", textTransform: "uppercase", color: "var(--ink-3)", marginBottom: 10 };
const h2: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: 32, letterSpacing: "-0.01em", color: "var(--ink)" };
const lede: CSSProperties = { fontSize: 16, lineHeight: 1.62, color: "var(--ink-2)", maxWidth: "62ch", marginTop: 12 };
const num: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "2.6rem", lineHeight: 1, fontFeatureSettings: "'tnum' 1", color: "var(--ink)" };
const cell: CSSProperties = { background: "var(--paper-raised)", padding: "22px 20px" };
const board: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 1, background: "var(--rule)", border: "1px solid var(--rule)", borderRadius: 12, overflow: "hidden", marginTop: 24 };
const th: CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", padding: "8px 12px", borderBottom: "1px solid var(--rule-strong)" };
const td: CSSProperties = { padding: "9px 12px", fontSize: 13.5, color: "var(--ink-2)", borderBottom: "1px solid var(--rule)", fontVariantNumeric: "tabular-nums" };
const cap: CSSProperties = { fontSize: 11.5, color: "var(--ink-3)", marginTop: 12 };

const Stat = ({ n, l, s }: { n: string; l: string; s?: string }) => (
  <div style={cell}>
    <div style={num}>{n}</div>
    <div style={{ fontSize: 13, color: "var(--ink-2)", marginTop: 8 }}>{l}</div>
    {s ? <div className="mono" style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 6 }}>{s}</div> : null}
  </div>
);
const Pending = ({ what, src }: { what: string; src: string }) => (
  <p className="mono" style={{ fontSize: 12.5, color: "var(--ink-3)", marginTop: 20, padding: "14px 16px", border: "1px dashed var(--rule-strong)", borderRadius: 10 }}>
    VALIDATION_PENDING &middot; {what} is staged on the pod, absent from this build. Reproduce from {src}.
  </p>
);
const BeforeAfter = ({ sport, a, b, src }: { sport: string; a: string; b: string; src: string }) => (
  <div style={{ ...cell, display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
    <span style={{ fontSize: 13, color: "var(--ink-2)", width: 84 }}>{sport}</span>
    <span style={{ ...num, fontSize: "2.1rem", color: "var(--ink-3)" }}>{a}</span>
    <span style={{ color: "var(--signal-ink)", fontSize: 20 }}>{"\u2192"}</span>
    <span style={{ ...num, fontSize: "2.4rem" }}>{b}</span>
    <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)", marginLeft: "auto" }}>{src}</span>
  </div>
);

export default function ForecasterPage() {
  return (
    <div className="wrap" style={{ paddingTop: 56, paddingBottom: 24 }}>
      <header>
        <div style={eye}>The Forecaster</div>
        <h1 className="serif" style={{ fontWeight: 500, fontSize: "clamp(2.6rem,5.5vw,4rem)", lineHeight: 1.05, letterSpacing: "-0.02em", color: "var(--ink)" }}>
          A calibrated engine, measured against itself.
        </h1>
        <p style={{ ...lede, fontSize: 18 }}>
          The market is efficient on price -- we proved it by rejecting our own pregame signals across four sports. So the honest question is not &ldquo;can we beat the close&rdquo; but &ldquo;does the machinery sharpen the forecast.&rdquo; It does, in one measured place: mid-game. Every number below wears its receipt, and no dollar edge is claimed.
        </p>
      </header>

      <section style={sec}>
        <div style={eye}>Walk-forward proof</div>
        <h2 style={h2}>Trained only on the past, scored on the future.</h2>
        <p style={lede}>
          An expanding-window backtest: every fold asserts <span className="mono">max_train_date &lt; min_test_date</span> or fails -- no K-fold on time-ordered games. The NBA win-probability ensemble across {wf ? wf.folds.length : 3} folds and {wf ? wf.seasons.join(" + ") : "two"} seasons; the widening train column is the walk forward itself.
        </p>
        {wf ? (
          <>
            <div style={board}>
              <Stat n={wf.acc_mean.toFixed(3)} l="Accuracy (mean)" s={`+/- ${wf.acc_std.toFixed(3)} across folds`} />
              <Stat n={f3(wf.brier_mean)} l="Brier (mean, lower better)" s={`+/- ${wf.brier_std.toFixed(3)}`} />
              <Stat n={`${wf.folds.length}`} l="Expanding folds" s={wf.seasons.join(" + ")} />
              <Stat n={`${wf.n_features}`} l="Leak-checked features" s="truncation-invariant" />
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 20, maxWidth: 560 }}>
              <thead><tr><th style={th}>Train frac</th><th style={th}>Train n</th><th style={th}>Val n</th><th style={th}>Acc</th><th style={th}>Brier</th></tr></thead>
              <tbody>
                {wf.folds.map((f, i) => (
                  <tr key={i}>
                    <td style={td}>{f.train_end_frac.toFixed(1)}</td><td style={td}>{f.n_train}</td><td style={td}>{f.n_val}</td><td style={td}>{f.acc.toFixed(3)}</td><td style={td}>{f3(f.brier)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mono" style={cap}>results/winprob_walk_forward_results.json &middot; 2026-07-20 &middot; edge_claimed: false</p>
          </>
        ) : (
          <Pending what="the walk-forward table" src="src/prediction/walk_forward_backtester.py" />
        )}
      </section>

      <section style={sec}>
        <div style={{ ...eye, color: "var(--signal-ink)" }}>The one measured win</div>
        <h2 style={h2}>In-game conditioning sharpens the forecast.</h2>
        <p style={lede}>
          Fusing the pregame rating prior with the realized mid-game state improves win-probability calibration on a real out-of-sample corpus. A live book also sees the score -- so this is calibration, not a claim of beating anyone.
        </p>
        <div style={{ ...board, gridTemplateColumns: "1fr" }}>
          <BeforeAfter sport="NBA Brier" a="0.209" b="0.159" src="proof_nba/ingame_accuracy.py" />
          <BeforeAfter sport="MLB Brier" a="0.241" b="0.126" src="proof_mlb/ingame_accuracy.py" />
        </div>
        <p style={{ ...lede, marginTop: 28 }}>
          <strong style={{ color: "var(--ink)" }}>But how much of that is skill?</strong> A rating-blind third arm -- conditioning on the score alone, no model prior -- splits the lift. Most of it is the scoreboard itself, free to anyone watching. The model&rsquo;s own contribution is the last column.
        </p>
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 16 }}>
          <thead><tr>
            <th style={th}>Sport</th><th style={th}>static (prior only)</th><th style={th}>score-only</th><th style={th}>combined</th><th style={th}>mechanical share</th><th style={th}>model-prior share</th>
          </tr></thead>
          <tbody>
            {ARMS.map((a) => (
              <tr key={a.sport}>
                <td style={{ ...td, color: "var(--ink)", fontWeight: 600 }}>{a.sport}</td>
                <td style={td}>{f3(a.stat)}</td><td style={td}>{f3(a.score)}</td>
                <td style={{ ...td, color: "var(--ink)", fontWeight: 600 }}>{f3(a.comb)}</td>
                <td style={td}>{a.mech}</td>
                <td style={{ ...td, color: "var(--signal-ink)", fontWeight: 600 }}>{a.prior}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mono" style={cap}>docs/INGAME_PROOF.md Sec. 2 + 2a &middot; real-corpus OOS &middot; VALIDATION_PENDING on a fresh clone &middot; edge_claimed: false</p>
        <ScoutNote envelope={{ status: "ok", prose: SCOUT_PROSE, chips: SCOUT_CHIPS }} />
      </section>

      <section style={sec}>
        <div style={eye}>What the model sees</div>
        <h2 style={h2}>Its own eyes: calibration by game state.</h2>
        <p style={lede}>
          Every graded in-game MLB prediction, bucketed by the model&rsquo;s probability band and the inning. Each cell is the calibration error -- how far the stated probability sits from what actually happened. Darker is a bigger gap: the improvement backlog, in the model&rsquo;s own view.
        </p>
        {scc ? (
          <>
            <div style={{ marginTop: 24 }}>
              <Grid rows={["Early (1-3)", "Mid (4-6)", "Late (7+)"]} cols={PROBS} values={gridVals}
                source="scripts/platformkit/analytics_showcase/out/state_conditioned_calibration.json" asOf="2026-07-23"
                title="MLB in-game calibration error (model)" valueFormat={(n) => n.toFixed(3)} verdict="descriptive_only"
                meta={`model ECE ${scc.sports.mlb.model_ece_n_weighted} vs market ${scc.sports.mlb.market_ece_n_weighted}`} />
            </div>
            <div style={{ marginTop: 40 }}>
              <Bars bars={backlog} source="state_conditioned_calibration.json (ranked_worst_buckets)" asOf="2026-07-23"
                title="Where the forecast is furthest from outcomes" eyebrow="Improvement backlog"
                valueFormat={(n) => n.toFixed(3)} unit="calib. error" verdict="descriptive_only" />
            </div>
          </>
        ) : (
          <Pending what="the state-conditioned grid" src="scripts/platformkit/analytics_showcase (state_conditioned_calibration)" />
        )}
      </section>

      <section style={sec}>
        <div style={eye}>Cross-sport scoreboard</div>
        <h2 style={h2}>Model vs market, every checkpoint, reported as-is.</h2>
        {cs ? (
          <>
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 20 }}>
              <thead><tr>
                <th style={th}>Sport</th><th style={th}>Market @ checkpoint</th><th style={th}>n</th><th style={th}>paired &Delta;</th><th style={th}>95% CI</th><th style={th}>verdict</th>
              </tr></thead>
              <tbody>
                {cs.rows.map((r, i) => {
                  const v = vtok(r.verdict);
                  return (
                    <tr key={i}>
                      <td style={{ ...td, color: "var(--ink)" }}>{sName(r.sport)}</td>
                      <td style={td}>{r.market} @ {r.checkpoint}</td>
                      <td style={td}>{r.n}</td>
                      <td style={td}>{sgn(r.paired_delta_mean)}</td>
                      <td style={{ ...td, color: "var(--ink-3)" }}>[{f3(r.paired_delta_95ci[0])}, {f3(r.paired_delta_95ci[1])}]</td>
                      <td style={td}><span className="mono" style={{ fontSize: 11.5, display: "inline-flex", alignItems: "center", gap: 6 }}>
                        <span className="dot" style={{ background: `var(--${dotVar(v)})` }} />{r.verdict.toLowerCase()}
                      </span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p style={{ ...lede, fontSize: 14.5, marginTop: 16 }}>{cs.honest_note}</p>
            <p className="mono" style={cap}>forecaster/cross_sport_scoreboard.json &middot; positive &Delta; = model sharper (paired) &middot; CI excluding 0 = a real gap &middot; edge_claimed: false</p>
          </>
        ) : (
          <Pending what="the cross-sport scoreboard" src="scripts/platformkit/benchmarks/crps_market/*" />
        )}
      </section>

      <section style={sec}>
        <div style={eye}>How a game moves</div>
        <h2 style={h2}>The aggregate transition explorer.</h2>
        <p style={lede}>
          No committed per-game trajectory exists to replay a single match honestly, so this is the aggregate: the calibrated win-probability swing carried by each adjacent-state transition, from the state grid above. Any in-game move decomposes into the transition it crossed.
        </p>
        {trans.length ? (
          <div style={{ marginTop: 24 }}>
            <Bars bars={trans} source="scripts/platformkit/analytics_showcase/out/why_attribution.json" asOf="2026-07-23"
              title="Largest calibrated win-probability swings" valueFormat={(n) => sgn(n, 3)} unit="win-prob" verdict="descriptive_only" />
          </div>
        ) : (
          <Pending what="the transition explorer" src="scripts/platformkit/analytics_showcase (why_attribution)" />
        )}
        <div style={{ marginTop: 28, padding: "18px 20px", border: "1px dashed var(--rule-strong)", borderRadius: 12, background: "var(--paper-tint)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span className="dot" style={{ boxShadow: "inset 0 0 0 1.5px var(--null)", background: "transparent" }} />
            <span style={eye}>Future exhibit &middot; pod-only</span>
          </div>
          <p style={{ fontSize: 15, lineHeight: 1.6, color: "var(--ink-2)", margin: 0 }}>
            <strong style={{ color: "var(--ink)" }}>Replay: watch the model think.</strong> Step through one real game&rsquo;s states with the win probability and its attribution at every tick, receipts attached. This needs committed per-game trajectory data, which lives only on the pod today -- so it is marked pending rather than mocked up. We never fabricate a trajectory.
          </p>
        </div>
      </section>

      <ScoutQuestions questions={QUESTIONS} heading="Ask Scout about the forecaster" />
    </div>
  );
}
