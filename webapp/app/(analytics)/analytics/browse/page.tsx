// Browse -- the analytics catalog (DESIGN Sec. 9 bento, IA "explore" surface).
// A build-time server component: reads site_manifest.json + joins each module's
// committed insight, derives an importance weight (rank-bucketed span, never
// hand-placed), and renders an importance-weighted bento that links each cell to
// /analytics/m/<id>. Filtering is a progressive-enhancement vanilla-JS script
// (the layout's pattern) so the page stays a server component -- no client file,
// no fetch, static-export clean. ASCII only.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import Link from "next/link";
import { VerdictDot, type Verdict } from "@/components/analytics/VerdictDot";

export const metadata: Metadata = {
  title: "Browse the analytics",
  description:
    "Every staged analytics module, importance-weighted and status-honest. Each cell links to the module's chart, receipts, and Scout note.",
};

const DATA = join(process.cwd(), "public", "data");

interface Mod {
  id: string;
  title: string;
  one_line?: string;
  chart_path?: string;
  status: string;
  as_of: string;
  evidence_page?: string;
}
interface Manifest {
  module_count: number;
  atlas_card_count: number;
  modules: Mod[];
}
interface Insight {
  headline_insight?: string;
  cited?: Array<{ field?: string; value?: unknown }>;
}

function readInsight(id: string): Insight | null {
  try {
    return JSON.parse(readFileSync(join(DATA, "insights", `${id}.json`), "utf-8"));
  } catch {
    return null;
  }
}

// Editorial category from the id -- a magazine "section", derived not curated.
function category(id: string): string {
  if (id.startsWith("ctx_")) return "Context";
  if (id.startsWith("cf_")) return "Counterfactual";
  if (id.startsWith("mlb_") || id.startsWith("statcast") || id === "pitch_sequencing") return "Baseball";
  if (id.startsWith("tennis_")) return "Tennis";
  if (id.startsWith("soccer_")) return "Soccer";
  if (id.startsWith("nba_")) return "Basketball";
  if (/calib|brier|murphy|residual/.test(id)) return "Calibration";
  if (/market|micro|tick|info_arrival|overreaction|convergence/.test(id)) return "Market";
  if (/mechanism|reject|fwd_claim|honesty|kernel|qa_|xsport|agent_fleet|dossier|cv_tracking/.test(id))
    return "The system";
  return "Analytics";
}

// status-honest verdict token: measured/descriptive modules read neutral (never
// green-as-praise, never red); an incomplete cut reads as a hollow pending ring.
function verdictOf(status: string): Verdict {
  return status === "ok" ? "descriptive_only" : "pending";
}

// Rank-by-completeness, then bucket to spans. No per-module placement: the top
// slice by score (chart + evidence + summary + ok-status, richer insight breaks
// ties) earns the flagship 2x2, the next slice 2x1, the rest 1x1.
function score(m: Mod, hl: number): number {
  return (m.status === "ok" ? 3 : 0) + (m.chart_path ? 2 : 0) + (m.evidence_page ? 1 : 0) + (m.one_line ? 1 : 0) + Math.min(hl, 1);
}

const FILTER_JS = `(function(){var g=document.getElementById('mbento');if(!g)return;var pills=document.querySelectorAll('[data-fpill]');function apply(f){var c=g.querySelectorAll('[data-cat]');for(var i=0;i<c.length;i++){c[i].style.display=(f==='all'||c[i].getAttribute('data-cat')===f)?'':'none';}for(var j=0;j<pills.length;j++){pills[j].classList.toggle('on',pills[j].getAttribute('data-fpill')===f);}}for(var k=0;k<pills.length;k++){pills[k].addEventListener('click',function(){apply(this.getAttribute('data-fpill'));});}})();`;

export default function BrowsePage() {
  const man: Manifest = JSON.parse(readFileSync(join(DATA, "showcase", "site_manifest.json"), "utf-8"));

  const rows = man.modules.map((m) => {
    const ins = readInsight(m.id);
    const summary = ins?.headline_insight || m.one_line || "";
    const c0 = ins?.cited?.[0]?.value;
    return { m, cat: category(m.id), summary, stat: c0 != null ? String(c0) : "", s: score(m, summary.length) };
  });
  rows.sort((a, b) => b.s - a.s || b.summary.length - a.summary.length || a.m.id.localeCompare(b.m.id));
  const withSpan = rows.map((r, i) => ({ ...r, span: i < 6 ? "b22" : i < 18 ? "b21" : "b11" }));

  const cats = Array.from(new Set(withSpan.map((r) => r.cat))).sort();

  return (
    <div className="wrap" style={{ paddingTop: 40, paddingBottom: 8 }}>
      <div className="overline">The catalog</div>
      <h1 className="serif" style={{ fontWeight: 500, fontSize: "clamp(2.4rem,5vw,3.4rem)", lineHeight: 1.05, letterSpacing: "-.02em", marginTop: 6 }}>
        Browse the analytics
      </h1>
      <p style={{ color: "var(--ink-2)", fontSize: 17, lineHeight: 1.6, maxWidth: 680, marginTop: 10 }}>
        {man.module_count} modules across four sports, joined to {man.atlas_card_count.toLocaleString()} entity cards. Every
        cell is measured and cited; nulls sit at full prominence, and no dollar edge is claimed.
      </p>

      <div className="mfilter" role="group" aria-label="Filter modules by section">
        <button className="on" data-fpill="all" type="button">All</button>
        {cats.map((c) => (
          <button key={c} data-fpill={c} type="button">{c}</button>
        ))}
      </div>

      <div id="mbento" className="mbento">
        {withSpan.map((r) => (
          <Link key={r.m.id} href={`/analytics/m/${r.m.id}`} className={`mcard ${r.span}`} data-cat={r.cat}>
            <div className="mc-top">
              <span className="mc-cat">{r.cat}</span>
              <VerdictDot verdict={verdictOf(r.m.status)} />
            </div>
            <div className="mc-title">{r.m.title}</div>
            {r.span !== "b11" && r.summary ? <div className="mc-sum">{r.summary}</div> : null}
            <div className="mc-foot">
              {r.stat && r.span !== "b11" ? <div className="mc-stat tnum">{r.stat}</div> : null}
              <div className="mc-chip mono">
                <VerdictDot verdict={verdictOf(r.m.status)} size={6} /> {r.m.as_of}
                {r.m.status !== "ok" ? " · partial" : ""}
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* eslint-disable-next-line react/no-danger */}
      <script dangerouslySetInnerHTML={{ __html: FILTER_JS }} />

      <style>{`
        .mfilter{display:flex;flex-wrap:wrap;gap:8px;margin:26px 0 22px}
        .mfilter button{font-family:var(--font-sans);font-size:13px;font-weight:500;color:var(--ink-2);
          background:var(--paper-raised);border:1px solid var(--rule-strong);border-radius:var(--radius-pill);
          padding:6px 14px;cursor:pointer;transition:color var(--dur-fast) var(--ease-ui),border-color var(--dur-fast) var(--ease-ui)}
        .mfilter button:hover{color:var(--ink);border-color:var(--accent)}
        .mfilter button.on{color:var(--accent-ink-on);background:var(--accent);border-color:var(--accent)}
        .mbento{display:grid;grid-template-columns:repeat(4,1fr);grid-auto-rows:158px;gap:16px}
        .mcard{background:var(--paper-raised);border:1px solid var(--rule);border-radius:var(--radius-card);
          padding:18px;box-shadow:var(--shadow-card);display:flex;flex-direction:column;position:relative;
          text-decoration:none;color:inherit;transition:box-shadow var(--dur-base) var(--ease-ui),border-color var(--dur-base) var(--ease-ui)}
        .mcard:hover{box-shadow:var(--shadow-raise);border-color:var(--accent);text-decoration:none}
        .mc-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
        .mc-cat{font-weight:700;font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:var(--ink-3)}
        .mc-title{font-weight:600;font-size:16px;line-height:1.25;margin-top:8px;color:var(--ink)}
        .mc-sum{font-size:13px;color:var(--ink-2);line-height:1.45;margin-top:6px;overflow:hidden;
          display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical}
        .mc-foot{margin-top:auto;display:flex;align-items:flex-end;justify-content:space-between;gap:10px;padding-top:10px}
        .mc-stat{font-family:var(--font-display);font-weight:500;font-size:1.7rem;line-height:1;color:var(--ink)}
        .mc-chip{font-size:11.5px;color:var(--ink-3);display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
        .b22{grid-column:span 2;grid-row:span 2}
        .b21{grid-column:span 2}
        .b22 .mc-title{font-size:20px}
        .b22 .mc-sum{-webkit-line-clamp:5}
        .b22 .mc-stat{font-size:2.4rem}
        @media(max-width:820px){.mbento{grid-template-columns:repeat(2,1fr)}.b22,.b21{grid-column:span 2}.b22{grid-row:auto}}
        @media(max-width:520px){.mbento{grid-template-columns:1fr;grid-auto-rows:auto}.mcard{min-height:150px}.b22,.b21{grid-column:auto}}
      `}</style>
    </div>
  );
}
