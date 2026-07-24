// Analytics HOME -- the first impression (DESIGN Sec. 8/9, IA Sec. 1-2, NIGHT_PLAN
// elevated goal). A build-time SERVER component: it readFileSync's the staged
// showcase JSON, so every number here is verbatim from its artifact and cited by a
// Receipt. Composition: Glass Court hero + one-line thesis + compact Ask Scout box,
// a four-number reproducibility scoreboard, a Scout note (tier-1 AI voice), doors to
// the crown surfaces (Forecaster / The Loop / Explore / Ask), an importance-weighted
// bento of flagship analytics, an honesty strip, and Scout deep-links. Nav + footer
// come from the route-group layout; this file renders only the page body. ASCII only.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import GlassCourt from "@/components/analytics/GlassCourt";
import { Bento, type BentoCell } from "@/components/analytics/Bento";
import { Receipt, type ReceiptData } from "@/components/analytics/Receipt";
import { ScoutNote } from "@/components/analytics/ScoutNote";
import { ScoutQuestions } from "@/components/analytics/ScoutQuestions";
import { VerdictLegend } from "@/components/analytics/VerdictLegend";
import { vtok } from "@/lib/analytics/verdict";
import { pickQuestions } from "@/lib/analytics/askPicks";

const BP = process.env.NEXT_PUBLIC_BASE_PATH || "";
const DIR = join(process.cwd(), "public", "data", "showcase");
const OUT = "scripts/platformkit/analytics_showcase/out";
const LEDGER = `${OUT}/mechanism_ledger_export.json`;

// Build-time reader with fresh-clone tolerance: a missing artifact returns null and
// the page falls back to the last verified constant (never blank, never fabricated).
// Python emits bare NaN into some artifacts (invalid JSON) -- sanitize before parse
// so a p-value NaN cannot crash the whole static build.
function readJson<T = any>(name: string): T | null {
  try {
    return JSON.parse(readFileSync(join(DIR, name), "utf-8").replace(/\bNaN\b/g, "null")) as T;
  } catch {
    return null;
  }
}
const fmt = (n: number) => n.toLocaleString("en-US");

// Home keeps the layout's default title ("CourtVision Analytics"); it only needs a
// home-specific description. Count-free on purpose so it never drifts from artifacts.
export const metadata = {
  description:
    "CourtVision Analytics: a calibrated multi-sport forecaster, a mechanism ledger of confirmed and null findings, and receipt-cited descriptive cards. The market is efficient; we aim to match the close. No dollar edge is claimed.",
};

export default function AnalyticsHome() {
  const manifest = readJson("site_manifest.json");
  const ledger = readJson("mechanism_ledger_export.json");
  const xsport = readJson("cross_sport_scoreboard.json");
  const honesty = readJson("honesty_exhibit.json");
  const fwd = readJson("fwd_claim_scoreboard.json");

  const moduleCount = manifest?.module_count ?? 54;
  const cardCount = manifest?.atlas_card_count ?? 1549;
  const checks = manifest?.checks_green ?? { pass: 63, total: 63 };
  const verd = ledger?.overall_counts ?? { confirmed: 130, null: 126, not_testable: 31, total: 287 };
  const confirms: number = verd.confirmed ?? 130;
  const nulls: number = verd.null ?? 126;
  const notTestable: number = verd.not_testable ?? 31;
  const xRows: number = xsport?.n_rows ?? 17;
  const endRow = (xsport?.rows || []).find(
    (r: any) => r.checkpoint === "end_q1" && /winprob/i.test(String(r.market))
  );
  const endDelta: string = Number.isFinite(endRow?.paired_delta_mean)
    ? endRow.paired_delta_mean.toFixed(4)
    : "-0.0084";
  const endN: number = endRow?.n ?? 1592;
  // Derive the verdict + source_artifact from the SAME row and the SAME vtok mapping
  // the Forecaster table uses, so this most-cited in-game figure never wears two
  // different honesty dots. This row is MARKET_SHARPER_PROVISIONAL -> "pending"
  // (hollow), not the solid "not_testable" this cell hardcoded before.
  const endStatus: string = endRow?.verdict ?? "MARKET_SHARPER_PROVISIONAL";
  const endVerdict = vtok(endStatus);
  const endSource: string =
    endRow?.source ?? "scripts/platformkit/benchmarks/crps_market/last_run_ingame_nba_winprob_ALLGAMES_v3.json";

  // one curated, verified example for the tier-1 Scout note (mechanism_ledger row
  // b2b_rest_penalty: effect -1.73, n=4732, CONFIRMED_LOCAL).
  const b2bChip: ReceiptData = { value: "-1.73", label: "CONFIRMED_LOCAL", sourceArtifact: LEDGER, n: 4732, corpus: "player_boxscores_2024_25_2025_26", verdict: "confirmed" };
  const ledgerChip: ReceiptData = { value: `${confirms} confirmed / ${nulls} null`, label: "mechanism_ledger_export", sourceArtifact: LEDGER, asOf: "2026-07-22", verdict: "descriptive_only" };

  const cells: BentoCell[] = [
    { href: `${BP}/analytics/the-loop`, category: "NBA \u00B7 Fatigue", title: "Back-to-Back Rest Penalty", summary: "Margin cost of a zero-rest game, leak-free over two seasons of team-game frames.", stat: "-1.73", statUnit: "pts", verdict: "confirmed", receipt: b2bChip, weight: "2x2", motif: true },
    // Lead with the plain verdict, not the raw 4-dp delta: a bare "-0.0084" reads as
    // a glitch next to the sibling stats. The number stays verbatim in the receipt.
    { href: `${BP}/analytics/forecaster`, category: "NBA \u00B7 In-game", title: "Win-Prob vs Market, End Q1", summary: `Paired Brier delta ${endDelta} against the close \u2014 negative means the market is still sharper.`, stat: "Market sharper", verdict: endVerdict, weight: "2x1",
      receipt: { value: endDelta, label: endStatus, n: endN, verdict: endVerdict, sourceArtifact: endSource } },
    { href: `${BP}/analytics/m/brier_skill_scores`, category: "MLB \u00B7 Skill", title: "Brier Skill Scores", stat: "Null", verdict: "null", weight: "1x1",
      receipt: { label: "descriptive_only -- model does not beat the market's Brier", sourceArtifact: `${OUT}/brier_skill_scores.json`, verdict: "null" } },
    { href: `${BP}/analytics/m/cross_sport_scoreboard`, category: "Cross-sport", title: "Calibration Scoreboard", stat: String(xRows), statUnit: "rows", verdict: "descriptive_only", weight: "1x1",
      receipt: { value: `${xRows} rows`, label: "composition only -- copied verbatim from source", sourceArtifact: `${OUT}/cross_sport_scoreboard.json`, verdict: "descriptive_only" } },
    { href: `${BP}/analytics/m/tennis_surface_transfer`, category: "Tennis \u00B7 Surface", title: "Surface Transfer", summary: "How a player's form carries across clay, grass, and hard courts.", stat: "278", statUnit: "players", verdict: "descriptive_only", weight: "2x1",
      receipt: { value: "278 players", label: "DESCRIPTIVE_ONLY", sourceArtifact: `${OUT}/atlas_tennis_manifest.json`, asOf: "2026-07-23", verdict: "descriptive_only" } },
  ];

  // The Loop door numbers derive from the SAME artifact /analytics/the-loop reads
  // (summary.n_families / summary.n_flipped), so the home page never desyncs from it
  // on a rerun. Fresh-clone fallback = the last verified 259/5 (never fabricated).
  const loopFamilies: number = fwd?.summary?.n_families ?? 259;
  const loopFlipped: number = fwd?.summary?.n_flipped ?? 5;

  const doors = [
    { href: `${BP}/analytics/forecaster`, title: "The Forecaster", meta: `${xRows} markets scored out-of-sample \u00B7 3 sports`,
      desc: "The calibrated prediction engine, walked forward and paired against the devigged close \u2014 calibration, never a dollar edge." },
    { href: `${BP}/analytics/the-loop`, title: "The Loop", meta: `${loopFamilies} forward-tested families \u00B7 ${loopFlipped} verdicts flipped`,
      desc: "The self-improving AI, keeping score on itself: propose, gate, verdict, then graveyard or verified." },
    { href: `${BP}/analytics/browse`, title: "Explore", meta: `${moduleCount} analytics modules`,
      desc: "Browse every analytic. Importance-weighted so a growing catalog stays scannable, nulls at equal prominence." },
    { href: `${BP}/analytics/ask`, title: "Ask Scout", meta: "precomputed \u00B7 receipt-cited \u00B7 no LLM at runtime",
      desc: "Ask a plain question. Scout answers only from precomputed, receipt-cited data, and says NO_DATA when it has none." },
  ];

  const board: Array<{ num: string; sub?: string; label: string; split?: boolean; chip: ReceiptData }> = [
    { num: fmt(cardCount), label: "entity cards \u00B7 4 sports", chip: { value: fmt(cardCount), label: "descriptive_only \u00B7 7 atlas manifests", sourceArtifact: `${OUT}/site_manifest.json`, asOf: "2026-07-23", verdict: "descriptive_only" } },
    { num: String(moduleCount), label: "analytics modules", chip: { value: String(moduleCount), label: "site_manifest.json", sourceArtifact: `${OUT}/site_manifest.json`, asOf: "2026-07-22", verdict: "descriptive_only" } },
    { num: String(verd.total ?? 287), label: "mechanism verdicts", split: true, chip: ledgerChip },
    { num: String(checks.pass ?? 63), sub: `/${checks.total ?? 63}`, label: "reproducibility checks green", chip: { value: `${checks.pass ?? 63}/${checks.total ?? 63}`, label: "site_manifest.checks_green · edge_claimed: false", sourceArtifact: `${OUT}/site_manifest.json`, asOf: "2026-07-23", verdict: "confirmed" } },
  ];

  // Verbatim corpus questions (status ok) so each pill phrase-resolves to a real
  // Scout answer instead of dead-ending on "No verified answer." Topical seeds ->
  // the on-subject ok entry; picked at build from the committed corpus.
  const questions = pickQuestions([
    "back-to-back second night hurt production",
    "beat betting market brier",
    "tennis prior surface transfer",
  ]);

  const scoutProse =
    `Playing on zero days rest costs an NBA team about **1.7 points of margin** \u2014 one of **${confirms} confirmed** ` +
    `mechanisms in the ledger. **${nulls}** more came back null, shown at equal prominence, because an honest null ` +
    `is a finding, not a failure.`;

  return (
    <div className="a-home wrap">
      <style>{CSS}</style>

      <section className="a-hero">
        <div>
          <div className="overline">Four sports &middot; every number cited</div>
          <h1>The analytics,<br className="a-hbr" />and the receipt<br className="a-hbr" />for every number.</h1>
          <p className="a-lede">
            A bottomless, honestly-measured look at basketball, baseball, soccer, and tennis.
            No edge claims &mdash; only calibrated findings you can check.
          </p>
          <form className="a-ask" action={`${BP}/analytics/ask`} method="get" role="search">
            <span className="a-ask-glyph" aria-hidden="true">{"\u25B2"}</span>
            <input type="text" name="q" placeholder="Ask Scout about a player, team, or metric..." aria-label="Ask Scout" />
            <button type="submit">Ask</button>
          </form>
          <p className="a-askrail">
            Scout answers only from precomputed, receipt-cited data. It never invents a number
            and says NO_DATA when it has none.
          </p>
        </div>
        <GlassCourt />
      </section>

      <div className="a-board">
        {board.map((c) => (
          <div key={c.label} className="a-bcell">
            <div className="a-bnum">
              {c.num}
              {c.sub ? <span className="sub">{c.sub}</span> : null}
            </div>
            <div className="a-blbl">{c.label}</div>
            {c.split ? (
              <div className="a-split">
                <span><span className="dot d-conf" />{confirms} confirmed</span>
                <span><span className="dot d-null" />{nulls} null</span>
                <span><span className="dot d-prov" />{notTestable} not testable</span>
              </div>
            ) : null}
            <div className="a-chiprow"><Receipt {...c.chip} /></div>
          </div>
        ))}
      </div>
      <p className="a-gloss">
        In plain terms: a <b>mechanism verdict</b> is one tested cause-and-effect claim;
        a <b>null</b> means we tested it and found nothing, and we keep those on purpose;
        a <b>Brier score</b> rates how calibrated a prediction is, where lower is better.
      </p>

      <ScoutNote envelope={{ status: "ok", prose: scoutProse, chips: [b2bChip, ledgerChip] }} />

      <div className="a-shead"><h2>Four ways in</h2></div>
      <div className="a-doors">
        {doors.map((d) => (
          <div key={d.href} className="a-door">
            <a className="k" href={d.href}>{d.title}</a>
            <p className="d">{d.desc}</p>
            <span className="m">{d.meta}</span>
          </div>
        ))}
      </div>

      <div className="a-shead">
        <h2>Explore the analytics</h2>
        <a href={`${BP}/analytics/browse`}>{`All ${moduleCount} modules \u2192`}</a>
      </div>
      <VerdictLegend style={{ margin: "-4px 0 18px" }} />
      <Bento cells={cells} />

      <div className="a-strip">
        <span className="k">The honest rail</span>
        <span className="t">
          {honesty?.headline ? honesty.headline + " \u2014 " : ""}
          The market is efficient; we aim to match the devigged close within noise. No dollar
          edge is claimed, anywhere. Every number links to the artifact that produced it, and
          the six retracted figures live only inside{" "}
          <a href={`${BP}/analytics/findings/retraction`}>their retraction</a>.
        </span>
      </div>

      <ScoutQuestions questions={questions} heading="Ask Scout about this" />
    </div>
  );
}

const CSS = `
.a-home{padding-bottom:8px}
.a-hero{display:grid;grid-template-columns:1.05fr .95fr;gap:44px;align-items:center;padding:60px 0 40px}
.a-hero h1{font-family:var(--font-display);font-weight:500;font-size:clamp(2.75rem,6vw,4.4rem);line-height:1.04;letter-spacing:-.02em;color:var(--ink);margin:14px 0 18px}
.a-lede{font-size:19px;line-height:1.6;color:var(--ink-2);max-width:36ch;margin-bottom:26px}
.a-ask{display:flex;align-items:center;gap:10px;background:var(--paper-raised);border:1px solid var(--rule-strong);border-radius:var(--radius-pill);padding:8px 8px 8px 16px;box-shadow:var(--shadow-card);max-width:460px}
.a-ask-glyph{width:22px;height:22px;border-radius:50%;background:var(--signal);color:var(--paper);display:grid;place-items:center;font-size:9px;line-height:1;flex:0 0 auto}
.a-ask input{border:0;background:transparent;flex:1;min-width:0;font-family:var(--font-sans);font-size:16px;color:var(--ink);outline:none}
.a-ask input::placeholder{color:var(--ink-3)}
.a-ask button{border:0;background:var(--accent);color:var(--accent-ink-on);font-weight:600;font-size:14px;padding:9px 18px;min-height:44px;border-radius:var(--radius-pill);cursor:pointer}
.a-askrail{font-size:12.5px;color:var(--ink-3);margin-top:10px;max-width:46ch;line-height:1.5}
.a-board{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:12px;margin:6px 0 8px}
.a-bcell{background:var(--paper-raised);padding:22px 20px;min-width:0}
.a-bnum{font-family:var(--font-display);font-weight:500;font-size:2.6rem;line-height:1;color:var(--ink);font-feature-settings:'tnum' 1}
.a-bnum .sub{font-size:1.4rem;color:var(--ink-3)}
.a-blbl{font-size:13px;color:var(--ink-2);margin-top:8px}
.a-split{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:10px;font-size:12px;color:var(--ink-3)}
.a-split span{display:inline-flex;align-items:center;gap:5px}
.a-chiprow{margin-top:10px}
.a-gloss{margin:12px 0 0;font-size:13.5px;line-height:1.55;color:var(--ink-3);max-width:78ch}
.a-gloss b{color:var(--ink-2);font-weight:600}
.a-shead{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin:46px 0 20px}
.a-shead h2{font-family:var(--font-display);font-weight:500;font-size:32px;letter-spacing:-.01em;color:var(--ink)}
.a-shead a{font-size:14px;font-weight:600;white-space:nowrap}
.a-doors{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
.a-door{position:relative;display:flex;flex-direction:column;padding:20px 18px;background:var(--paper-raised);border:1px solid var(--rule);border-radius:var(--radius-card);box-shadow:var(--shadow-card);transition:box-shadow .22s var(--ease-ui),border-color .22s var(--ease-ui),transform .22s var(--ease-ui)}
.a-door:hover,.a-door:focus-within{box-shadow:var(--shadow-raise);border-color:var(--accent);transform:translateY(-2px)}
.a-door .k{font-family:var(--font-display);font-weight:500;font-size:20px;color:var(--ink)}
.a-door .k:hover{text-decoration:none}
.a-door .k::after{content:"";position:absolute;inset:0}
.a-door .d{font-size:13.5px;line-height:1.5;color:var(--ink-2);margin:8px 0 0;flex:1 1 auto}
.a-door .m{font-family:var(--font-mono);font-size:11.5px;color:var(--ink-3);margin-top:14px}
.a-strip{border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);padding:22px 0;margin:48px 0 8px;display:flex;gap:16px;align-items:baseline}
.a-strip .k{font-weight:700;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--signal-ink);white-space:nowrap}
.a-strip .t{color:var(--ink-2);font-size:14.5px;line-height:1.6;max-width:78ch}
@media(max-width:900px){.a-doors,.a-board{grid-template-columns:repeat(2,1fr)}}
@media(max-width:820px){.a-hero{grid-template-columns:1fr;gap:30px;padding:36px 0 26px}}
/* Drop the hard hero breaks on phones: at the clamp's 2.75rem floor the forced
   third line ("for every number.") overflows a ~342px box and rags to a 4th/5th
   line. Removing the <br>s lets Fraunces wrap at word boundaries -- no overflow,
   clean rag -- while desktop keeps its deliberate three-line stack. */
@media(max-width:560px){.a-doors,.a-board{grid-template-columns:1fr}.a-strip{flex-direction:column;gap:8px}.a-hero h1 br.a-hbr{display:none}.a-shead{flex-direction:column;align-items:flex-start;gap:6px}}
`;
