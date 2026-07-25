// Module detail -- one analytics module as a reading-room page (IA explore/[module]).
// Build-time server component: joins the module's manifest row + committed out JSON
// + committed insight. Renders the committed chart in the editorial Figure frame,
// a Scout note (insight -> envelope, NO_DATA-honest), a receipt table of the cited
// facts, a confound/caveat block, and -- for modules that carry them -- a novelty
// (prior-art verdict + formula) block. generateStaticParams = every manifest id.
// No client fetch, no live data; ASCII only.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Figure } from "@/components/analytics/charts/Figure";
import { ScoutNote, type ScoutEnvelope } from "@/components/analytics/ScoutNote";
import { ScoutQuestions } from "@/components/analytics/ScoutQuestions";
import type { ReceiptData } from "@/components/analytics/Receipt";
import { VerdictLegend } from "@/components/analytics/VerdictLegend";
import { NovelStatPanel, type NovelStat, windowText } from "@/components/analytics/NovelStatPanel";
import { asOfDate } from "@/lib/analytics/format";

const DATA = join(process.cwd(), "public", "data");
const BASE = process.env.NEXT_PUBLIC_BASE_PATH || "";

interface Mod {
  id: string;
  title: string;
  one_line?: string;
  out_path: string;
  chart_path?: string;
  status: string;
  as_of: string;
  evidence_page?: string;
}
interface Cite { field?: string; value?: unknown; path?: string }
interface Insight {
  title?: string;
  headline_insight?: string;
  what_it_means?: string;
  how_to_read?: string;
  why_it_matters?: string;
  caveat?: string;
  cited?: Cite[];
}
type Out = Record<string, unknown>;

const readJson = <T,>(p: string): T | null => {
  try {
    return JSON.parse(readFileSync(p, "utf-8")) as T;
  } catch {
    return null;
  }
};
const base = (p: string) => p.split(/[\\/]/).pop() || p;
const str = (v: unknown) => (v == null ? "" : String(v));
// A cited row is a real receipt fact only if its value is a scalar/non-empty
// array that is not a build-status placeholder. Keeps numbers, booleans, non-
// empty strings, and non-empty arrays; drops null/empty and the not_buildable
// family of sentinels that render as blank or unfinished in the receipts table.
const SENTINEL = /^(not_buildable|not_available|not_testable|unavailable|no_data)$/i;
const isFact = (v: unknown): boolean => {
  if (v == null) return false;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "string") return v.trim() !== "" && !SENTINEL.test(v.trim());
  return typeof v === "number" || typeof v === "boolean";
};

function getMod(id: string): Mod | undefined {
  const man = readJson<{ modules: Mod[] }>(join(DATA, "showcase", "site_manifest.json"));
  return man?.modules.find((m) => m.id === id);
}

// one_line is the fan-facing subtitle -- it surfaces as the on-page mv-sub, the
// <meta name="description">/link-preview text, and the chart alt. Some manifest
// rows carry the raw build token "DESCRIPTIVE_ONLY" (or are blank), which must
// never leak to any of those. Treat those as absent and fall back to the committed
// headline_insight (the same field the page already reads).
const subtitleOf = (m: Mod, ins: Insight | null): string => {
  const ol = (m.one_line || "").trim();
  if (ol && !/^descriptive_only$/i.test(ol)) return ol;
  return (ins?.headline_insight || "").trim();
};

// Only surface Scout pills whose answer actually lives in the committed corpus.
// Match ask entries to this module by its source artifact (basename == id), keep
// the answerable (status ok) ones, and use their VERBATIM corpus question -- so the
// pill is guaranteed to phrase-resolve, never dead-end. Mirrors the entity page's
// insight gate; the old templated "What does X measure?" strings hit NO_DATA (or a
// mismatched closest cite) for ~96% of modules. No hit -> no pills (honest).
function corpusQuestions(id: string): string[] {
  const c = readJson<{ entries?: Array<{ q: string; a?: { source_artifact?: string; status?: string } }> }>(
    join(DATA, "ask", "corpus.json")
  );
  const stem = (p?: string) => (p || "").split(/[\\/]/).pop()?.replace(/\.[a-z0-9]+$/i, "") || "";
  const hits = (c?.entries || []).filter(
    (e) => e.a?.status === "ok" && (stem(e.a?.source_artifact) === id || (e.a?.source_artifact || "").includes(`/${id}.`))
  );
  return Array.from(new Set(hits.map((e) => e.q))).slice(0, 3);
}

export function generateStaticParams() {
  const man = readJson<{ modules: Mod[] }>(join(DATA, "showcase", "site_manifest.json"));
  return (man?.modules || []).map((m) => ({ id: m.id }));
}

export function generateMetadata({ params }: { params: { id: string } }): Metadata {
  const m = getMod(params.id);
  if (!m) return { title: "Module", description: "A measured, receipt-cited analytics module." };
  // Title mirrors the page's own H1 (ins?.title || m.title), so the browser tab and
  // link preview no longer read a raw machine string the H1 already rescued.
  const ins = readJson<Insight>(join(DATA, "insights", `${m.id}.json`));
  return {
    title: ins?.title || m.title,
    description: subtitleOf(m, ins) || "A measured, receipt-cited analytics module.",
  };
}

function Box({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mv-box">
      <h3 className="serif">{title}</h3>
      {children}
    </div>
  );
}

export default function ModulePage({ params }: { params: { id: string } }) {
  const m = getMod(params.id);
  if (!m) notFound();

  const out = readJson<Out>(join(DATA, "showcase", `${m.id}.json`)) || {};
  const ins = readJson<Insight>(join(DATA, "insights", `${m.id}.json`));
  // The receipts panel IS the honesty proof, so it must never show a fact-less
  // row: drop cited entries whose value is empty/null or a build-status sentinel
  // (a "not_buildable" string or blank cell reads as unfinished). Filter once, so
  // both the receipt chips and the table below inherit the clean set. Non-empty
  // arrays (e.g. seasons_available) stay -- String() renders them as "a,b,c".
  const cited = (ins?.cited || []).filter((c) => isFact(c.value));
  // out.method is a string on most modules but a nested methodology object on a
  // few (cf_star_removal, ctx_player_splits). String({}) prints "[object Object]",
  // so render a plain string as prose and an object as a key/value definition list
  // (below) -- never String() the dict, never silently drop it.
  const methodStr = typeof out.method === "string" ? out.method.trim() : "";
  const methodPairs =
    out.method && typeof out.method === "object" && !Array.isArray(out.method)
      ? Object.entries(out.method as Record<string, unknown>)
      : [];
  const descriptive = out.descriptive_only === true || /descriptive/i.test(ins?.caveat || "");
  // Machine timestamps in the manifest as_of collapse to a clean date; descriptive
  // corpus labels ("2025-26 regular season ...") pass through untouched. Falls back
  // to the raw value so it stays a non-empty string for the required Figure asOf.
  const asOf = asOfDate(m.as_of) || m.as_of;
  const sub = subtitleOf(m, ins);
  // as_of says when the artifact was built; it does NOT say what span of data it
  // saw. Any module whose out JSON declares observation_window prints that span
  // in the provenance line -- schema-driven, no module list.
  const win = windowText(out.observation_window);

  const chips: ReceiptData[] = cited.slice(0, 4).map((c) => ({
    value: str(c.value),
    label: c.field,
    sourceArtifact: c.path || m.out_path,
    asOf,
    verdict: "descriptive_only",
  }));
  const envelope: ScoutEnvelope = ins
    ? { status: descriptive ? "descriptive_only" : "ok", prose: ins.headline_insight || "", chips }
    : { status: "no_data", prose: "" };

  const chartSrc = m.chart_path ? `${BASE}/img/showcase/${base(m.chart_path)}` : null;
  const confounds = out.declared_confounds;
  const confoundList = Array.isArray(confounds) ? (confounds as string[]) : confounds ? [str(confounds)] : [];
  // The six novel_* modules carry a full paper-shaped artifact (headline, metric
  // definition, formula, results rows, prior art, confounds, exclusions). The old
  // inline mv-novel block rendered only the verdict + formula and dropped the rest,
  // so those modules get the dedicated panel instead -- and the caveat block stops
  // repeating the confound list the panel already prints.
  const isNovel = m.id.startsWith("novel_") && typeof out.stat_name === "string" && typeof out.formula === "string";
  const hasNovelty =
    !isNovel && !!(out.prior_art_verdict || out.formula || out.prior_art || out.prior_art_citation || out.metric_definition);

  const questions = corpusQuestions(m.id);

  return (
    <div className="wrap" style={{ paddingTop: 8 }}>
      <div className="mv-crumbs">
        <Link href="/analytics/browse">Browse</Link> &rsaquo; {m.title}
      </div>
      {descriptive ? (
        <div className="mv-banner">
          <span className="dot d-desc" /> Descriptive only &mdash; a measured pattern, no edge claimed.
        </div>
      ) : null}

      <div className="mv-head">
        <div>
          <div className="overline">
            Analytics module &middot; as of {asOf}
            {win ? <> &middot; data {win}</> : null}
          </div>
          <h1 className="serif">{ins?.title || m.title}</h1>
          {sub ? <div className="mv-sub">{sub}</div> : null}
        </div>
        {chartSrc ? (
          // Open the native-resolution PNG in a new tab (not a file download) so a
          // phone reader can pinch-zoom the baked-in axis ticks / n= labels instead of
          // squinting at the shrunk inline figure.
          <a className="mv-dl" href={chartSrc} target="_blank" rel="noopener">
            View full size &#8599;
          </a>
        ) : null}
      </div>

      <VerdictLegend style={{ margin: "0 0 24px" }} />

      <div className="mv-grid">
        <div style={{ minWidth: 0 }}>
          {chartSrc ? (
            <Figure source={m.out_path} asOf={asOf} title={m.title} verdict="descriptive_only">
              {/* committed module chart; basePath prefixed manually (not a next/image).
                  The PNG is baked on a white ground, so seat it on a CONSTANT light mat
                  (a hardcoded ivory, never a theme token -- --paper-tint flips dark) so it
                  never sits as a glaring white block in dark mode. The mat also carries a
                  min-width so the figure scrolls at a legible size on a phone inside the
                  Figure frame (like the SVG charts) instead of shrinking its baked labels
                  to microtype; "View full size" above pinch-zooms the native-res PNG. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <div style={{ minWidth: 560, background: "#FBF7EF", padding: 8, borderRadius: 8, border: "1px solid var(--rule)" }}>
                <img src={chartSrc} alt={sub ? `Chart: ${m.title} -- ${sub}` : `${m.title} chart`} style={{ width: "100%", height: "auto", display: "block", borderRadius: 4 }} />
              </div>
            </Figure>
          ) : (
            <div className="mv-nochart mono">No committed chart for this module &mdash; the receipts below are the evidence.</div>
          )}

          <ScoutNote envelope={envelope} />

          {ins?.what_it_means ? (
            <div className="mv-prose">
              <h2 className="overline" style={{ marginBottom: 8 }}>What it means</h2>
              <p>{ins.what_it_means}</p>
            </div>
          ) : null}

          {(ins?.caveat || methodStr || methodPairs.length || (!isNovel && confoundList.length)) ? (
            <div className="mv-caveat">
              <h2 className="overline" style={{ color: "var(--signal-ink)", marginBottom: 8 }}>Caveats &amp; confounds</h2>
              {ins?.caveat ? <p>{ins.caveat}</p> : null}
              {methodStr ? (
                <p style={{ marginTop: 8 }}>
                  <b>Method.</b> {methodStr}
                </p>
              ) : methodPairs.length ? (
                <div style={{ marginTop: 8 }}>
                  <p style={{ margin: 0 }}><b>Method.</b></p>
                  <dl className="mv-method">
                    {methodPairs.map(([k, v]) => (
                      <div key={k}>
                        <dt>{k.replace(/_/g, " ")}</dt>
                        <dd className="mono">{str(v)}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ) : null}
              {!isNovel && confoundList.length ? (
                <ul>
                  {confoundList.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {isNovel ? <NovelStatPanel stat={out as NovelStat} /> : null}

          {hasNovelty ? (
            <div className="mv-novel">
              <div className="mv-novel-top">
                <h2 className="overline">Novelty &amp; prior art</h2>
                {out.prior_art_verdict ? <span className="mv-verdict">{str(out.prior_art_verdict)}</span> : null}
              </div>
              {out.metric_definition ? <p>{str(out.metric_definition)}</p> : null}
              {out.formula ? <pre className="mv-formula mono">{str(out.formula)}</pre> : null}
              {(out.prior_art_citation || out.prior_art) ? (
                <p className="mv-priorart">
                  <b>Prior art.</b> {str(out.prior_art_citation || out.prior_art)}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>

        <aside className="mv-side">
          <Box title="Receipts">
            {cited.length ? (
              <table className="mv-rtable">
                <tbody>
                  {cited.map((c, i) => (
                    <tr key={i}>
                      <td className="mv-rf">{c.field || "value"}</td>
                      <td className="mv-rv tnum">{str(c.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>No cited facts staged.</p>
            )}
            <div className="mv-src mono">{cited[0]?.path || m.out_path}</div>
            {win ? <div className="mv-src mono">observation window: {win}</div> : null}
          </Box>

          {ins?.how_to_read ? (
            <Box title="How to read it">
              <p style={{ fontSize: 14, color: "var(--ink-2)", lineHeight: 1.55 }}>{ins.how_to_read}</p>
            </Box>
          ) : null}

          <Box title="Where it appears">
            <div className="mv-links">
              {/* The evidence pages live in the separate terminal product (docs/
                  evidence/*.md, no in-Reading-Room route), so a bare filename here
                  read as a broken link. Dropped -- the receipts above already cite
                  this module's source artifact. */}
              <Link href="/analytics/browse">Back to the catalog</Link>
              <Link href="/analytics/the-loop">Mechanism ledger</Link>
            </div>
          </Box>
        </aside>
      </div>

      <ScoutQuestions questions={questions} />

      <style dangerouslySetInnerHTML={{ __html: `
        .mv-crumbs{font-size:13px;color:var(--ink-3);padding:22px 0 6px}
        .mv-crumbs a{color:var(--ink-3)}
        .mv-banner{display:inline-flex;align-items:center;gap:8px;background:var(--paper-tint);
          border:1px solid var(--rule-strong);border-radius:8px;padding:8px 14px;font-size:13px;color:var(--ink-2);margin:8px 0 26px}
        .mv-head{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;
          border-bottom:1px solid var(--rule-strong);padding-bottom:22px;margin-bottom:30px}
        .mv-head h1{font-family:var(--font-display);font-weight:500;font-size:clamp(2.2rem,4.6vw,3.2rem);line-height:1.06;letter-spacing:-.02em;margin-top:4px}
        .mv-sub{color:var(--ink-2);margin-top:8px;font-size:16px;max-width:60ch}
        .mv-dl{border:1px solid var(--rule-strong);border-radius:8px;padding:9px 15px;font-size:13px;font-weight:600;color:var(--accent);white-space:nowrap}
        .mv-grid{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:40px;align-items:start}
        .mv-prose{margin-top:28px;max-width:680px}
        .mv-prose p{font-size:16.5px;line-height:1.62;color:var(--ink-2)}
        .mv-caveat{margin-top:24px;background:var(--paper-tint);border:1px solid var(--rule);border-radius:var(--radius-card);padding:18px 20px;max-width:680px}
        .mv-caveat p{font-size:14.5px;line-height:1.58;color:var(--ink-2)}
        .mv-caveat b{color:var(--ink)}
        .mv-caveat ul{margin:8px 0 0 18px}
        .mv-caveat li{font-size:14px;color:var(--ink-2);line-height:1.5;margin-top:4px}
        .mv-method{margin:6px 0 0;font-size:13.5px}
        .mv-method>div{display:flex;gap:12px;padding:5px 0;border-bottom:1px solid var(--rule)}
        .mv-method>div:last-child{border-bottom:0}
        .mv-method dt{color:var(--ink-3);flex:0 0 42%;line-height:1.45}
        .mv-method dd{margin:0;color:var(--ink);flex:1 1 0;min-width:0;overflow-wrap:anywhere;line-height:1.45}
        .mv-novel{margin-top:24px;border:1px solid var(--rule-strong);border-radius:var(--radius-card);
          padding:18px 20px;max-width:680px;border-top:3px solid var(--signal)}
        .mv-novel-top{display:flex;align-items:center;gap:12px;margin-bottom:10px}
        .mv-verdict{font-family:var(--font-mono);font-size:11px;font-weight:500;letter-spacing:.08em;
          color:var(--signal-ink);border:1px solid var(--rule-strong);border-radius:var(--radius-chip);padding:2px 8px}
        .mv-novel p{font-size:14.5px;line-height:1.58;color:var(--ink-2)}
        .mv-novel b{color:var(--ink)}
        .mv-formula{margin:12px 0;background:var(--paper-tint);border:1px solid var(--rule);border-radius:8px;
          padding:12px 14px;font-size:12.5px;color:var(--ink);white-space:pre-wrap;word-break:break-word;line-height:1.5}
        .mv-priorart{margin-top:10px}
        .mv-nochart{background:var(--paper-tint);border:1px dashed var(--rule-strong);border-radius:var(--radius-card);
          padding:20px;font-size:13px;color:var(--ink-3)}
        .mv-box{background:var(--paper-raised);border:1px solid var(--rule);border-radius:var(--radius-card);
          padding:18px;box-shadow:var(--shadow-card);margin-bottom:20px}
        .mv-box h3{font-family:var(--font-display);font-weight:500;font-size:19px;margin-bottom:12px}
        .mv-rtable{width:100%;border-collapse:collapse}
        .mv-rtable td{padding:7px 0;border-bottom:1px solid var(--rule);vertical-align:top;font-size:13px}
        .mv-rtable tr:last-child td{border-bottom:0}
        .mv-rf{color:var(--ink-3);padding-right:12px;line-height:1.4}
        /* wrap long cited values (some reasons/raw_cache run 90-170 chars): nowrap
           forced a ~1000px cell that blew the fixed 320px receipts rail past the
           viewport (horizontal scroll on phones, broken 2-col grid on desktop).
           Short numbers -- the common case -- still sit on one line. */
        .mv-rv{font-family:var(--font-mono);color:var(--ink);text-align:right;white-space:normal;overflow-wrap:anywhere}
        .mv-src{font-size:11px;color:var(--ink-3);margin-top:12px;word-break:break-all;line-height:1.5}
        .mv-links{display:flex;flex-direction:column;gap:9px;font-size:14px}
        .mv-links a{color:var(--accent)}
        @media(max-width:820px){.mv-grid{grid-template-columns:minmax(0,1fr)}.mv-head{flex-wrap:wrap}}
      ` }} />
    </div>
  );
}
