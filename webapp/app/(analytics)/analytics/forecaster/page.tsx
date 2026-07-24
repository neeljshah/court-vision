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
import { scrollFrame } from "@/components/analytics/charts/Figure";
import { Bars, type BarDatum } from "@/components/analytics/charts/Bars";
import { ScoutNote } from "@/components/analytics/ScoutNote";
import { ScoutQuestions } from "@/components/analytics/ScoutQuestions";
import { Receipt } from "@/components/analytics/Receipt";
import { VerdictDot } from "@/components/analytics/VerdictDot";
import { VerdictLegend } from "@/components/analytics/VerdictLegend";
import { vtok } from "@/lib/analytics/verdict";
import { pickQuestions } from "@/lib/analytics/askPicks";

export const metadata = {
  title: "The Forecaster",
  description:
    "The calibrated prediction engine: walk-forward, leak-free scoring across three sports, with the in-game static-to-conditional Brier improvement as the centerpiece. Matched against the devigged close; no dollar edge is claimed.",
};

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
type TrState = { time: string; prob: string; mean_y: number; n: number };
type Tr = { sport: string; from: TrState; to: TrState; winprob_delta: number; min_support_n: number };

const wf = fc<WF>("winprob_walk_forward_results.json");
const scc = fc<SCC>("state_conditioned_calibration.json");
const cs = fc<{ rows: Row[]; honest_note: string }>("cross_sport_scoreboard.json");
const why = fc<{ biggest_drops: Tr[]; biggest_gains: Tr[] }>("../why_attribution.json");

const f3 = (n: number) => n.toFixed(3);
const sgn = (n: number, d = 4) => `${n >= 0 ? "+" : ""}${n.toFixed(d)}`;
const SPORT: Record<string, string> = { nba: "NBA", mlb: "MLB", mlb_ingame: "MLB (in-game)", mlb_pregame: "MLB (pregame)", soccer_intl: "Soccer" };
const sName = (s: string) => SPORT[s] || s;
const tShort = (t: string) => t.split("(")[0];
// vtok (verdict-string -> honesty token) lives in lib/analytics/verdict so the Home
// bento cell and this table map the SAME scoreboard row to the SAME dot.

// "what the model sees": pivot MLB model buckets into a time x prob-band grid
const TIMES = ["early(inn1-3)", "mid(inn4-6)", "late(inn7+)"];
const PROBS = ["0-.2", ".2-.4", ".4-.6", ".6-.8", ".8-1"];
const gridVals: (number | null)[][] = TIMES.map((t) =>
  PROBS.map((p) => scc?.sports.mlb?.buckets.find((x) => x.source === "model" && x.time_bucket === t && x.prob_bucket === p)?.calibration_error ?? null)
);
const backlog: BarDatum[] = (scc?.ranked_worst_buckets ?? []).slice(0, 6).map((b) => ({
  label: `${sName(b.sport)} ${tShort(b.time_bucket)} ${b.prob_bucket}`, value: b.calibration_error, sub: `n=${b.n}`, color: "var(--signal)",
}));
// A bucket whose realized rate is exactly 0 or 1 has no measurable swing -- every
// game in it resolved the same way, so the "delta" is thin one-sided support, not a
// move. Drop those, then keep one row per (sport, destination state) so a single
// to-state can't render as twin identical bars.
const isDegenerate = (s: TrState) => s.mean_y === 0 || s.mean_y === 1;
const cleanTrans = (rows: Tr[]) => {
  const seen = new Set<string>();
  return rows.filter((t) => {
    if (isDegenerate(t.from) || isDegenerate(t.to)) return false;
    const k = `${t.sport}|${t.to.time}|${t.to.prob}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
};
const allTrans: Tr[] = why ? [...why.biggest_drops, ...why.biggest_gains] : [];
const keptTrans = cleanTrans(allTrans);
const nDegenerate = allTrans.filter((t) => isDegenerate(t.from) || isDegenerate(t.to)).length;
const nDeduped = allTrans.length - nDegenerate - keptTrans.length;
const trans: BarDatum[] = [
  ...keptTrans.filter((t) => t.winprob_delta < 0).slice(0, 3),
  ...keptTrans.filter((t) => t.winprob_delta > 0).slice(0, 3),
].map((t) => ({
  label: `${sName(t.sport)} ${tShort(t.from.time)}->${tShort(t.to.time)}`, value: t.winprob_delta,
  sub: `${t.from.prob}->${t.to.prob}  n>=${t.min_support_n}`, color: "var(--accent)",
}));

// In-game three-arm decomposition -- verbatim from committed docs/INGAME_PROOF.md
// Sec. 2 + 2a. That doc is tracked, so the narrative renders on every clone; the
// live re-run prints VALIDATION_PENDING off-corpus (private corpora absent on a
// fresh clone), so the receipt is pending on RE-RUN, not on publication.
const ARMS = [
  { sport: "NBA", stat: 0.209, score: 0.172, comb: 0.159, mech: "~73%", prior: "-0.014 (~27%)" },
  { sport: "MLB", stat: 0.241, score: 0.128, comb: 0.126, mech: "~99%", prior: "-0.001 (~1%)" },
];
const SCOUT_CHIPS: Parameters<typeof Receipt>[0][] = [
  { label: "CALIBRATION_OOS -- receipt published in-repo; live re-run VALIDATION_PENDING without the private corpus", sourceArtifact: "docs/INGAME_PROOF.md", asOf: "2026-07-23", verdict: "pending" },
  { label: "BSS vs market -- null is the exhibit", sourceArtifact: "scripts/platformkit/analytics_showcase/out/brier_skill_scores.json", asOf: "2026-07-24", n: 78986, verdict: "null" },
  { label: "walk-forward, expanding window", sourceArtifact: "results/winprob_walk_forward_results.json", asOf: "2026-07-20", verdict: "confirmed" },
];
const SCOUT_PROSE =
  "Pregame, the forecaster **matches** the devigged close within noise and beats nothing. The one measured win is **in-game**: conditioning NBA win-probability on the realized state sharpens calibration to Brier **0.159** \u2014 but most of that lift is the scoreboard itself, and the model's own prior adds only the last **~0.014**. Against the market's Brier, skill is **near or below zero** across sports; that null is the point, not a defect.";
// Verbatim corpus questions (status ok) so each pill phrase-resolves to a real
// Scout answer instead of the "No verified answer" closest-cite fallback.
const QUESTIONS = pickQuestions([
  "in-game conditioning sharpen calibration",
  "beat market pregame closing-line",
  "widest calibration gap weakest",
]);

// styles
const sec: CSSProperties = { marginTop: 64 };
const eye: CSSProperties = { fontWeight: 700, fontSize: 11, letterSpacing: "0.13em", textTransform: "uppercase", color: "var(--ink-3)", marginBottom: 10 };
const h2: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: 32, letterSpacing: "-0.01em", color: "var(--ink)" };
const lede: CSSProperties = { fontSize: 16, lineHeight: 1.62, color: "var(--ink-2)", maxWidth: "62ch", marginTop: 12 };
const num: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "2.6rem", lineHeight: 1, fontFeatureSettings: "'tnum' 1", color: "var(--ink)" };
const cell: CSSProperties = { background: "var(--paper-raised)", padding: "22px 20px" };
const board: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 1, background: "var(--rule)", border: "1px solid var(--rule)", borderRadius: 12, overflow: "hidden", marginTop: 24 };
// nowrap so the overflowX:auto wrappers actually scroll on a phone (a width:100%
// table with wrapping cells never overflows -- it just crams into a lattice).
const th: CSSProperties = { textAlign: "left", fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", padding: "8px 12px", borderBottom: "1px solid var(--rule-strong)", whiteSpace: "nowrap" };
const td: CSSProperties = { padding: "9px 12px", fontSize: 13.5, color: "var(--ink-2)", borderBottom: "1px solid var(--rule)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" };
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
    VALIDATION_PENDING &middot; {what} is a live exhibit we haven&rsquo;t published yet. Source: {src}.
  </p>
);
// Numbers are deliberately restrained (not a triumphal hero size) and the arrow is
// neutral ink, not amber -- a Brier drop that is mostly the scoreboard must not read
// as a big model "win" ahead of the decomposition that qualifies it.
const BeforeAfter = ({ sport, a, b, src }: { sport: string; a: string; b: string; src: string }) => (
  <div style={{ ...cell, display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
    <span style={{ fontSize: 13, color: "var(--ink-2)", width: 84 }}>{sport}</span>
    <span style={{ ...num, fontSize: "1.6rem", color: "var(--ink-3)" }}>{a}</span>
    <span style={{ color: "var(--ink-3)", fontSize: 17 }}>{"\u2192"}</span>
    <span style={{ ...num, fontSize: "1.8rem", color: "var(--ink-2)" }}>{b}</span>
    {/* The one number on the page that had a bare filename instead of a hover
        receipt. Give it the same Receipt every other figure wears -- verdict
        pending on live RE-RUN (the private corpus is absent on a fresh clone),
        not pending on publication -- the source doc is committed. */}
    <span style={{ marginLeft: "auto" }}>
      <Receipt sourceArtifact={src} label="CALIBRATION_OOS -- receipt published in-repo; live re-run VALIDATION_PENDING without the private corpus" asOf="2026-07-23" verdict="pending" />
    </span>
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
          The market is efficient on price &mdash; we proved it by rejecting our own pregame signals across three sports. So the honest question is not &ldquo;can we beat the close&rdquo; but &ldquo;does the machinery sharpen the forecast.&rdquo; It does, in one measured place: mid-game. Every number below wears its receipt, and no dollar edge is claimed.
        </p>
        <VerdictLegend style={{ marginTop: 22 }} />
      </header>

      <section style={sec}>
        <div style={eye}>Walk-forward proof</div>
        <h2 style={h2}>Trained only on the past, scored on the future.</h2>
        <p style={lede}>
          An expanding-window backtest: every fold asserts <span className="mono">max_train_date &lt; min_test_date</span> or fails &mdash; no K-fold on time-ordered games. The NBA win-probability ensemble across {wf ? wf.folds.length : 3} folds and {wf ? wf.seasons.join(" + ") : "two"} seasons; the widening train column is the walk forward itself.
        </p>
        {wf ? (
          <>
            <div style={board}>
              <Stat n={wf.acc_mean.toFixed(3)} l="Accuracy (mean)" s={`+/- ${wf.acc_std.toFixed(3)} across folds`} />
              <Stat n={f3(wf.brier_mean)} l="Brier (mean, lower better)" s={`+/- ${wf.brier_std.toFixed(3)}`} />
              <Stat n={`${wf.folds.length}`} l="Expanding folds" s={wf.seasons.join(" + ")} />
              <Stat n={`${wf.n_features}`} l="Leak-checked features" s="truncation-invariant" />
            </div>
            <div style={scrollFrame}><table className="fc-tbl" style={{ width: "100%", borderCollapse: "collapse", marginTop: 20, maxWidth: 560 }}>
              <thead><tr><th scope="col" style={th}>Train frac</th><th scope="col" style={th}>Train n</th><th scope="col" style={th}>Val n</th><th scope="col" style={th}>Acc</th><th scope="col" style={th}>Brier</th></tr></thead>
              <tbody>
                {wf.folds.map((f, i) => (
                  <tr key={i}>
                    <td style={td}>{f.train_end_frac.toFixed(1)}</td><td style={td}>{f.n_train}</td><td style={td}>{f.n_val}</td><td style={td}>{f.acc.toFixed(3)}</td><td style={td}>{f3(f.brier)}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
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
          Fusing the pregame rating prior with the realized mid-game state improves win-probability calibration on a real out-of-sample corpus. A live book also sees the score &mdash; so this is calibration, not a claim of beating anyone.
        </p>
        {/* overflow:visible (board defaults to hidden to clip its 12px corners) so the
            BeforeAfter receipts' top:100% popover isn't sliced off; Receipt self-flips
            to stay on-screen, so no page scroll. */}
        <div style={{ ...board, gridTemplateColumns: "1fr", overflow: "visible" }}>
          <BeforeAfter sport="NBA Brier" a="0.209" b="0.159" src="proof_nba/ingame_accuracy.py" />
          <BeforeAfter sport="MLB Brier" a="0.241" b="0.126" src="proof_mlb/ingame_accuracy.py" />
        </div>
        <p style={{ ...cap, marginTop: 10 }}>
          Read this as calibration, not a win: most of the drop is the scoreboard state itself, free to anyone watching &mdash; the model&rsquo;s own prior adds only the last sliver, decomposed below.
        </p>
        <p style={{ ...lede, marginTop: 28 }}>
          <strong style={{ color: "var(--ink)" }}>But how much of that is skill?</strong> A rating-blind third arm &mdash; conditioning on the score alone, no model prior &mdash; splits the lift. Most of it is the scoreboard itself, free to anyone watching. The model&rsquo;s own contribution is the last column.
        </p>
        <div style={scrollFrame}><table className="fc-tbl" style={{ width: "100%", borderCollapse: "collapse", marginTop: 16 }}>
          <thead><tr>
            <th scope="col" style={th}>Sport</th><th scope="col" style={th}>static (prior only)</th><th scope="col" style={th}>score-only</th><th scope="col" style={th}>combined</th><th scope="col" style={th}>mechanical share</th><th scope="col" style={th}>model-prior share</th>
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
        </table></div>
        <p className="mono" style={cap}>docs/INGAME_PROOF.md Sec. 2 + 2a &middot; real-corpus OOS &middot; each arm rounded independently to 3 dp; the share column is derived from full precision, so it will not reconcile to the 3-dp cells &middot; source doc committed in this repo; live re-run prints VALIDATION_PENDING without the private corpus and falls back to this recorded table &middot; edge_claimed: false</p>
        <ScoutNote envelope={{ status: "ok", prose: SCOUT_PROSE, chips: SCOUT_CHIPS }} />
      </section>

      <section style={sec}>
        <div style={eye}>What the model sees</div>
        <h2 style={h2}>Its own eyes: calibration by game state.</h2>
        <p style={lede}>
          Every graded in-game MLB prediction, bucketed by the model&rsquo;s probability band and the inning. Each cell is the calibration error &mdash; how far the stated probability sits from what actually happened. Darker is a bigger gap: the improvement backlog, in the model&rsquo;s own view.
        </p>
        {scc ? (
          <>
            <div style={{ marginTop: 24 }}>
              <Grid rows={["Early (1-3)", "Mid (4-6)", "Late (7+)"]} cols={PROBS} values={gridVals}
                source="scripts/platformkit/analytics_showcase/out/state_conditioned_calibration.json" asOf="2026-07-23"
                title="MLB in-game calibration error (model)" valueFormat={(n) => n.toFixed(3)} verdict="descriptive_only"
                /* Scroll at the product-standard 560 min-width (like every other chart)
                   so the cell values stay legible on a phone. At the earlier fit-to-phone
                   ~340 the SVG scaled ~0.47 and the cell numbers rendered at ~5.7px,
                   unreadable without pinch-zoom. Trade-off: swiping right to the .6-.8/.8-1
                   columns briefly scrolls the Early/Mid/Late row labels off the left (SVG
                   can't sticky a column) -- a smaller harm across only 3 fixed-order rows
                   than microtype in every cell; the colour ramp stays the primary read. */
                minWidth={560}
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
            <div style={scrollFrame}><table className="fc-tbl" style={{ width: "100%", borderCollapse: "collapse", marginTop: 20 }}>
              <thead><tr>
                <th scope="col" style={th}>Sport</th><th scope="col" style={th}>Market @ checkpoint</th><th scope="col" style={th}>n</th><th scope="col" style={th}>model vs market (paired)</th><th scope="col" style={th}>95% CI</th><th scope="col" style={th}>verdict</th>
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
                        <VerdictDot verdict={v} />{r.verdict.replace(/_/g, " ").toLowerCase()}
                      </span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table></div>
            <p style={{ ...lede, fontSize: 14.5, marginTop: 16 }}>{cs.honest_note}</p>
            <p className="mono" style={cap}>forecaster/cross_sport_scoreboard.json &middot; positive &Delta; = model sharper (paired) &middot; a sharper verdict needs the CI clear of 0 AND enough n &middot; edge_claimed: false</p>
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
            <p style={cap}>
              Filtered: {nDegenerate} of {allTrans.length} candidate transitions are excluded because one end sits in a degenerate bucket &mdash; a realized rate of exactly 0.000 or 1.000, where every game in the bucket resolved the same way. Those buckets have no measurable swing to report; their apparent delta is thin one-sided support, not a move.
              {nDeduped > 0 ? ` A further ${nDeduped} were collapsed so a single destination state renders one bar, not duplicates.` : " Rows are also de-duplicated by destination state so one to-state cannot render as twin bars."}
              {" "}What remains is what the data actually supports, which is mostly MLB and soccer.
            </p>
          </div>
        ) : (
          <Pending what="the transition explorer" src="scripts/platformkit/analytics_showcase (why_attribution)" />
        )}
        <div style={{ marginTop: 28, padding: "18px 20px", border: "1px dashed var(--rule-strong)", borderRadius: 12, background: "var(--paper-tint)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span className="dot" style={{ boxShadow: "inset 0 0 0 1.5px var(--null)", background: "transparent" }} />
            <span style={eye}>Future exhibit &middot; not yet published</span>
          </div>
          <p style={{ fontSize: 15, lineHeight: 1.6, color: "var(--ink-2)", margin: 0 }}>
            <strong style={{ color: "var(--ink)" }}>Replay: watch the model think.</strong> Step through one real game&rsquo;s states with the win probability and its attribution at every tick, receipts attached. This needs committed per-game trajectory data, which we haven&rsquo;t published yet &mdash; so it is marked pending rather than mocked up. We never fabricate a trajectory.
          </p>
        </div>
      </section>

      <ScoutQuestions questions={QUESTIONS} heading="Ask Scout about the forecaster" />

      {/* Pin the first column so scrolling right to reach the off-screen verdict /
          CI columns on a phone never loses the row's Sport/label anchor (matches
          players/page.tsx .pl-tbl). The scrollFrame wrappers add the edge-fade cue
          that the scroll exists. --paper bg blends with the page under the pin. */}
      <style>{`
        .fc-tbl th:first-child,.fc-tbl td:first-child{position:sticky;left:0;z-index:1;background:var(--paper);box-shadow:1px 0 0 var(--rule-strong)}
        .fc-tbl thead th:first-child{z-index:2}
      `}</style>
    </div>
  );
}
