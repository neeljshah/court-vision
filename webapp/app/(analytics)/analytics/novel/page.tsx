// Novel statistics -- the six prior-art-gated, adversarially re-derived stats this
// system published that did not exist before it. Build-time server component: reads
// public/data/showcase/novel_stats_index.json + each module's own novel_*.json and
// renders name/abbrev, the headline number LARGE, the one-line definition, the
// prior-art verdict chip, the declared-confound count, and the receipt (source
// artifact + as_of). Every number is lifted verbatim from the committed artifact --
// nothing is computed here beyond picking which row leads the card. Descriptive
// only, edge_claimed:false on every stat. ASCII only.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Novel statistics",
  description:
    "Six statistics that did not exist before this system -- each gated against prior art, adversarially re-derived, and published with its confounds. Descriptive only, no edge claimed.",
};

const DATA = join(process.cwd(), "public", "data", "showcase");

interface Card {
  stat_name: string;
  abbrev: string;
  module: string;
  prior_art_verdict: string;
  headline: string;
  is_honest_null?: boolean;
  source_artifacts?: string[];
}
interface Index {
  generated_at?: string;
  n_stats?: number;
  stats: Card[];
}
type Row = Record<string, unknown>;
interface Novel {
  metric_definition?: string;
  formula?: string;
  as_of?: unknown;
  declared_confounds?: string[];
  prior_art_citation?: string;
  results?: unknown;
}

const readJson = <T,>(f: string): T | null => {
  try {
    return JSON.parse(readFileSync(join(DATA, f), "utf-8")) as T;
  } catch {
    return null;
  }
};
const baseName = (p: string) => p.split(/[\\/]/).pop() || p;
const n0 = (v: unknown) => Number(v).toLocaleString("en-US");

interface Lead {
  value: string;
  unit: string;
  caption: string;
}

// One picker per stat: which committed row leads the card. Values are printed as
// they sit in the artifact (no rounding, no re-derivation) -- only the choice of
// row is made here, and each caption names the row it came from.
function leadOf(mod: string, d: Novel): Lead | null {
  const rows = (Array.isArray(d.results) ? d.results : []) as Row[];
  const top = (score: (r: Row) => number): Row | null =>
    rows.length ? rows.reduce((a, b) => (score(b) > score(a) ? b : a)) : null;
  const s = (v: unknown) => String(v);

  if (mod === "novel_line_half_life") {
    const r = top((x) => Number(x.n_move_pairs) || 0);
    if (!r) return null;
    return {
      value: s(r.half_life_label),
      unit: "hours before tip",
      caption: `${s(r.sport)} -- half of all pre-game line motion is complete by then; n=${n0(r.n_move_pairs)} move pairs, final-hour share ${s(r.final_hour_movement_share)}`,
    };
  }
  if (mod === "novel_live_clock_fraction") {
    const r = top((x) => Number(x.live_clock_fraction) || 0);
    if (!r) return null;
    return {
      value: s(r.live_clock_fraction),
      unit: "of the clock still contested",
      caption: `${s(r.sport)} -- ${n0(r.n_games_decided)} of ${n0(r.n_games_total)} games decided at a ${s(r.near_median_threshold)}-${s(r.unit)} gap`,
    };
  }
  if (mod === "novel_load_bearing_index") {
    const r = top((x) => Number((x.estimator_a_elo_onoff as Row)?.delta_winprob) || 0);
    if (!r) return null;
    const a = r.estimator_a_elo_onoff as Row;
    return {
      value: s(a.delta_winprob),
      unit: "win-prob swing on one player",
      caption: `${s(r.team)} -- ${s(a.player_name)}, Elo on/off net-rating delta ${s(a.on_off_net_rating_delta)}; the second estimator names a different player (agreement 1 of 30 teams)`,
    };
  }
  if (mod === "novel_market_foresight_premium") {
    const res = (d.results || {}) as Record<string, Row>;
    const keys = Object.keys(res);
    if (!keys.length) return null;
    const k = keys.reduce((a, b) => (Number(res[b].mfp_mean) > Number(res[a].mfp_mean) ? b : a));
    const r = res[k];
    return {
      value: s(r.mfp_mean),
      unit: "excess resolving power per bit",
      caption: `${k} -- mean over ${s(r.n_checkpoints)} in-game checkpoints; the market's lead rises ${s(r.mfp_first)} to ${s(r.mfp_last)} as the game runs`,
    };
  }
  if (mod === "novel_overreaction_harvest_gap") {
    const r = top((x) => Number(x.ohg) || 0);
    if (!r) return null;
    return {
      value: s(r.ohg),
      unit: "harvest gap (a measured failure)",
      caption: `${s(r.sport)} -- the market overshoots ${s(r.overreaction_abs_mean)} on big in-game moves, yet our model is the closer forecast only ${s(r.model_can_beat_model_closer_rate)} of the time at max disagreement (n=${n0(r.max_disagreement_n)})`,
    };
  }
  if (mod === "novel_schedule_fatigue_tax") {
    const r = top((x) => -Number(x.sft_credible_pts_per100_ortg) || 0);
    if (!r) return null;
    return {
      value: s(r.sft_credible_pts_per100_ortg),
      unit: "pts/100 ORtg, season-averaged",
      caption: `${s(r.team)} ${s(r.season)} -- the most congested schedule of ${rows.length} team-seasons; ${s(r.b2b_games)} back-to-backs (frequency ${s(r.b2b_freq)})`,
    };
  }
  return null;
}

const asOfOf = (d: Novel, fallback: string) =>
  typeof d.as_of === "string" && d.as_of ? d.as_of : fallback;

const GATE: Array<[string, string]> = [
  ["Prior-art search", "The definition is searched against the published literature and the public analytics canon before anything is built. The verdict is written down even when it is unflattering -- INCREMENTAL means someone got most of the way here first, and the card says so."],
  ["Buildability check", "The stat must be computable from artifacts already committed in this repo. No new scrape, no private feed, no number that cannot be recomputed from the cited source files."],
  ["Adversarial re-derivation", "The result is rebuilt a second time, by a different route where one exists, specifically to break it. Load-Bearing Index ships with two independent estimators that disagree on 29 of 30 teams -- that disagreement is printed, not hidden."],
  ["Declared confounds", "Every stat publishes what would make it wrong: sparse tail buckets, excluded sports, absolute-move churn, conflated model misspecification. Confounds are part of the stat, not an appendix."],
  ["edge_claimed: false", "These are market-science and descriptive measurements. None of them is a profit claim, and each artifact carries the flag saying so."],
];

export default function NovelStatsPage() {
  const idx = readJson<Index>("novel_stats_index.json");
  const stats = idx?.stats || [];
  const stamp = (idx?.generated_at || "").slice(0, 10);

  const cards = stats.map((c) => {
    const d = readJson<Novel>(`${c.module}.json`) || {};
    return { c, d, lead: leadOf(c.module, d), asOf: asOfOf(d, stamp) };
  });

  return (
    <div className="wrap nv">
      <p className="overline">Novel statistics</p>
      <h1 className="serif nv-h1">Six statistics that did not exist before this system</h1>
      <p className="nv-lede">
        Each one was searched against prior art before it was built, re-derived a
        second time to try to break it, and published with the confounds that could
        make it wrong. They are descriptive market science and structure measurements
        &mdash; every artifact carries <span className="mono">edge_claimed: false</span>,
        and none of them is a profit claim.
      </p>
      <p className="nv-meta mono">
        {cards.length} stats &middot; index generated {stamp} &middot; each number below is lifted
        verbatim from its committed artifact
      </p>

      <div className="nv-grid">
        {cards.map(({ c, d, lead, asOf }, i) => (
          <article key={c.module} className={`nv-card${c.is_honest_null ? " is-null" : ""}`}>
            <div className="nv-top">
              <span className="mono nv-n">{String(i + 1).padStart(2, "0")}</span>
              <span className="mono nv-verdict">
                <span className={`dot ${c.is_honest_null ? "d-null" : "d-desc"}`} />
                {c.prior_art_verdict}
              </span>
            </div>
            <h2 className="serif nv-name">
              {c.stat_name} <span className="mono nv-abbrev">{c.abbrev}</span>
            </h2>
            {d.metric_definition ? <p className="nv-def">{d.metric_definition}</p> : null}

            {lead ? (
              <div className="nv-figure">
                <div className="nv-value tnum">{lead.value}</div>
                <div className="nv-unit">{lead.unit}</div>
                <p className="nv-cap">{lead.caption}</p>
              </div>
            ) : null}

            {c.is_honest_null ? (
              <p className="nv-nullnote">
                <b>A published null is a result, not a failure.</b> This stat measures our
                own inability to convert a real market overshoot. It is on this page at
                full size because the ones that do not work are the reason to trust the
                ones that do.
              </p>
            ) : null}

            <div className="nv-foot">
              <div className="mono nv-src">
                {(c.source_artifacts || []).map((p) => (
                  <div key={p}>{baseName(p)}</div>
                ))}
                <div className="nv-asof">as of {asOf}</div>
                {d.declared_confounds?.length ? (
                  <div className="nv-asof">{d.declared_confounds.length} confounds declared</div>
                ) : null}
              </div>
              <Link className="nv-link" href={`/analytics/m/${c.module}`}>
                Formula, results table and prior art &rarr;
              </Link>
            </div>
          </article>
        ))}
      </div>

      <section className="nv-gate">
        <p className="overline">How a stat gets published here</p>
        <h2 className="serif nv-h2">Five gates, and the verdict is printed either way</h2>
        <ol className="nv-steps">
          {GATE.map(([t, body], i) => (
            <li key={t}>
              <span className="mono nv-step-n">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <h3 className="nv-step-t">{t}</h3>
                <p>{body}</p>
              </div>
            </li>
          ))}
        </ol>
        <p className="nv-close">
          Nothing on this page is a betting edge. The claim is narrower and harder:
          these are measurements that are honest about their own limits, and you can
          recompute every one of them from the artifacts named on the cards.
        </p>
      </section>

      <style>{`
        .nv{padding:48px 24px 72px}
        .nv-h1{font-weight:500;font-size:clamp(2.1rem,4.4vw,3.1rem);line-height:1.07;letter-spacing:-.02em;margin-top:10px;max-width:19ch}
        .nv-lede{margin-top:18px;max-width:660px;font-size:17px;line-height:1.66;color:var(--ink-2)}
        .nv-lede .mono{font-size:15px;color:var(--ink)}
        .nv-meta{margin-top:16px;font-size:12px;color:var(--ink-3);padding-bottom:26px;border-bottom:1px solid var(--rule-strong)}
        .nv-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:26px;margin-top:34px}
        .nv-card{display:flex;flex-direction:column;background:var(--paper-raised);border:1px solid var(--rule);
          border-top:3px solid var(--signal);border-radius:var(--radius-card);padding:22px 24px 20px;box-shadow:var(--shadow-card)}
        .nv-card.is-null{border-top-color:var(--null)}
        .nv-top{display:flex;align-items:center;justify-content:space-between;gap:12px}
        .nv-n{font-size:12px;color:var(--ink-3)}
        .nv-verdict{display:inline-flex;align-items:center;gap:7px;font-size:10.5px;letter-spacing:.08em;
          color:var(--ink-2);border:1px solid var(--rule-strong);border-radius:var(--radius-chip);padding:3px 9px}
        .nv-name{font-weight:500;font-size:25px;letter-spacing:-.01em;margin-top:12px;line-height:1.2}
        .nv-abbrev{font-size:13px;color:var(--ink-3);letter-spacing:.06em;margin-left:6px}
        .nv-def{margin-top:9px;font-size:14.5px;line-height:1.56;color:var(--ink-2)}
        .nv-figure{margin-top:18px;padding-top:16px;border-top:1px solid var(--rule)}
        .nv-value{font-family:var(--font-display);font-weight:500;font-size:clamp(3rem,6.5vw,4.1rem);
          line-height:.98;letter-spacing:-.03em;color:var(--ink)}
        .nv-unit{margin-top:6px;font-size:13.5px;color:var(--ink-2)}
        .nv-cap{margin-top:10px;font-size:13px;line-height:1.55;color:var(--ink-3)}
        .nv-nullnote{margin-top:16px;background:var(--paper-tint);border-left:2px solid var(--null);
          border-radius:0 8px 8px 0;padding:12px 14px;font-size:13.5px;line-height:1.58;color:var(--ink-2)}
        .nv-nullnote b{color:var(--ink)}
        .nv-foot{margin-top:auto;padding-top:18px}
        .nv-src{font-size:11px;line-height:1.7;color:var(--ink-3);word-break:break-all}
        .nv-asof{color:var(--ink-3);opacity:.85}
        .nv-link{display:inline-block;margin-top:12px;font-size:13.5px;font-weight:600;color:var(--accent)}
        .nv-gate{margin-top:64px;padding-top:40px;border-top:1px solid var(--rule-strong);max-width:760px}
        .nv-h2{font-weight:500;font-size:clamp(1.6rem,3vw,2.1rem);letter-spacing:-.015em;margin-top:10px}
        .nv-steps{list-style:none;margin-top:26px}
        .nv-steps li{display:flex;gap:18px;padding:18px 0;border-top:1px solid var(--rule)}
        .nv-step-n{font-size:12px;color:var(--signal-ink);flex:0 0 auto;padding-top:3px}
        .nv-step-t{font-size:15px;font-weight:700;color:var(--ink)}
        .nv-steps p{margin-top:5px;font-size:14.5px;line-height:1.6;color:var(--ink-2)}
        .nv-close{margin-top:26px;font-size:15px;line-height:1.65;color:var(--ink-2);
          border-left:2px solid var(--signal);padding-left:16px}
        @media(max-width:860px){.nv-grid{grid-template-columns:minmax(0,1fr)}}
      `}</style>
    </div>
  );
}
