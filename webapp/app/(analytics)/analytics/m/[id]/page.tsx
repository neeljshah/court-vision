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

function getMod(id: string): Mod | undefined {
  const man = readJson<{ modules: Mod[] }>(join(DATA, "showcase", "site_manifest.json"));
  return man?.modules.find((m) => m.id === id);
}

export function generateStaticParams() {
  const man = readJson<{ modules: Mod[] }>(join(DATA, "showcase", "site_manifest.json"));
  return (man?.modules || []).map((m) => ({ id: m.id }));
}

export function generateMetadata({ params }: { params: { id: string } }): Metadata {
  const m = getMod(params.id);
  return { title: m ? m.title : "Module", description: m?.one_line || "A measured, receipt-cited analytics module." };
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
  const cited = ins?.cited || [];
  const descriptive = out.descriptive_only === true || /descriptive/i.test(ins?.caveat || "");

  const chips: ReceiptData[] = cited.slice(0, 4).map((c) => ({
    value: str(c.value),
    label: c.field,
    sourceArtifact: c.path || m.out_path,
    asOf: m.as_of,
    verdict: "descriptive_only",
  }));
  const envelope: ScoutEnvelope = ins
    ? { status: descriptive ? "descriptive_only" : "ok", prose: ins.headline_insight || "", chips }
    : { status: "no_data", prose: "" };

  const chartSrc = m.chart_path ? `${BASE}/img/showcase/${base(m.chart_path)}` : null;
  const confounds = out.declared_confounds;
  const confoundList = Array.isArray(confounds) ? (confounds as string[]) : confounds ? [str(confounds)] : [];
  const hasNovelty = !!(out.prior_art_verdict || out.formula || out.prior_art || out.prior_art_citation || out.metric_definition);

  const questions = [
    `What does ${m.title} measure?`,
    `Which sports does ${m.title} cover?`,
    `How is ${m.title} calculated?`,
  ];

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
          <div className="overline">Analytics module &middot; as of {m.as_of}</div>
          <h1 className="serif">{ins?.title || m.title}</h1>
          {m.one_line ? <div className="mv-sub">{m.one_line}</div> : null}
        </div>
        {chartSrc ? (
          <a className="mv-dl" href={chartSrc} download>
            Download chart PNG &darr;
          </a>
        ) : null}
      </div>

      <div className="mv-grid">
        <div style={{ minWidth: 0 }}>
          {chartSrc ? (
            <Figure source={m.out_path} asOf={m.as_of} title={m.title} verdict="descriptive_only">
              {/* committed module chart; basePath prefixed manually (not a next/image) */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={chartSrc} alt={`${m.title} chart`} style={{ width: "100%", height: "auto", display: "block", borderRadius: 8, border: "1px solid var(--rule)" }} />
            </Figure>
          ) : (
            <div className="mv-nochart mono">No committed chart for this module &mdash; the receipts below are the evidence.</div>
          )}

          <ScoutNote envelope={envelope} />

          {ins?.what_it_means ? (
            <div className="mv-prose">
              <div className="overline" style={{ marginBottom: 8 }}>What it means</div>
              <p>{ins.what_it_means}</p>
            </div>
          ) : null}

          {(ins?.caveat || str(out.method) || confoundList.length) ? (
            <div className="mv-caveat">
              <div className="overline" style={{ color: "var(--signal-ink)", marginBottom: 8 }}>Caveats &amp; confounds</div>
              {ins?.caveat ? <p>{ins.caveat}</p> : null}
              {str(out.method) ? (
                <p style={{ marginTop: 8 }}>
                  <b>Method.</b> {str(out.method)}
                </p>
              ) : null}
              {confoundList.length ? (
                <ul>
                  {confoundList.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {hasNovelty ? (
            <div className="mv-novel">
              <div className="mv-novel-top">
                <span className="overline">Novelty &amp; prior art</span>
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
          </Box>

          {ins?.how_to_read ? (
            <Box title="How to read it">
              <p style={{ fontSize: 14, color: "var(--ink-2)", lineHeight: 1.55 }}>{ins.how_to_read}</p>
            </Box>
          ) : null}

          <Box title="Where it appears">
            <div className="mv-links">
              {m.evidence_page ? (
                <span>
                  Evidence page <span className="why mono">{base(m.evidence_page)}</span>
                </span>
              ) : null}
              <Link href="/analytics/browse">Back to the catalog</Link>
              <Link href="/analytics/the-loop">Mechanism ledger</Link>
            </div>
          </Box>
        </aside>
      </div>

      <ScoutQuestions questions={questions} />

      <style>{`
        .mv-crumbs{font-size:13px;color:var(--ink-3);padding:22px 0 6px}
        .mv-crumbs a{color:var(--ink-3)}
        .mv-banner{display:inline-flex;align-items:center;gap:8px;background:var(--paper-tint);
          border:1px solid var(--rule-strong);border-radius:8px;padding:8px 14px;font-size:13px;color:var(--ink-2);margin:8px 0 26px}
        .mv-head{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;
          border-bottom:1px solid var(--rule-strong);padding-bottom:22px;margin-bottom:30px}
        .mv-head h1{font-family:var(--font-display);font-weight:500;font-size:clamp(2.2rem,4.6vw,3.2rem);line-height:1.06;letter-spacing:-.02em;margin-top:4px}
        .mv-sub{color:var(--ink-2);margin-top:8px;font-size:16px;max-width:60ch}
        .mv-dl{border:1px solid var(--rule-strong);border-radius:8px;padding:9px 15px;font-size:13px;font-weight:600;color:var(--accent);white-space:nowrap}
        .mv-grid{display:grid;grid-template-columns:1fr 320px;gap:40px;align-items:start}
        .mv-prose{margin-top:28px;max-width:680px}
        .mv-prose p{font-size:16.5px;line-height:1.62;color:var(--ink-2)}
        .mv-caveat{margin-top:24px;background:var(--paper-tint);border:1px solid var(--rule);border-radius:var(--radius-card);padding:18px 20px;max-width:680px}
        .mv-caveat p{font-size:14.5px;line-height:1.58;color:var(--ink-2)}
        .mv-caveat b{color:var(--ink)}
        .mv-caveat ul{margin:8px 0 0 18px}
        .mv-caveat li{font-size:14px;color:var(--ink-2);line-height:1.5;margin-top:4px}
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
        .mv-rv{font-family:var(--font-mono);color:var(--ink);text-align:right;white-space:nowrap}
        .mv-src{font-size:11px;color:var(--ink-3);margin-top:12px;word-break:break-all;line-height:1.5}
        .mv-links{display:flex;flex-direction:column;gap:9px;font-size:14px}
        .mv-links a{color:var(--accent)}
        .mv-links .why{color:var(--ink-3);font-size:11px}
        @media(max-width:820px){.mv-grid{grid-template-columns:1fr}.mv-head{flex-wrap:wrap}}
      `}</style>
    </div>
  );
}
