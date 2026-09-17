import Link from "next/link";
import { Figure } from "@/components/analytics/charts/Figure";
import { RelatedReading } from "@/components/analytics/RelatedReading";
import { ScoutNote, type ScoutEnvelope } from "@/components/analytics/ScoutNote";
import { VerdictLegend } from "@/components/analytics/VerdictLegend";
import { artifactUrl, provenanceDate } from "@/lib/analytics/artifactProvenance";
import { classifyModuleEvidence } from "@/lib/analytics/moduleEvidence";
import { getPublishedChartPresentation } from "@/lib/analytics/publishedChartPresentation";
import { noticesForModules } from "@/lib/analytics/dataIntegrity";
import type { Cite, Insight, Mod, Out } from "@/app/(analytics)/analytics/m/[id]/page";
import { DataIntegrityNotice } from "@/components/analytics/DataIntegrityNotice";
import { ModuleEvidence } from "./ModuleEvidence";
import { ModuleReadingGuide } from "./ModuleReadingGuide";

const base = process.env.NEXT_PUBLIC_BASE_PATH || "";
const sentinel = /^(not_buildable|not_available|not_testable|unavailable|no_data)$/i;
const fact = (value: unknown) => value != null && (Array.isArray(value) ? value.length > 0 : typeof value !== "string" || (!!value.trim() && !sentinel.test(value.trim())));
const text = (value: unknown) => value == null ? "" : String(value);
const name = (path?: string) => path?.split(/[\\/]/).pop() || "";
type FigureData = { headers: string[]; rows: Array<Record<string, unknown>> };

function fallbackData(out: Out): FigureData {
  const teams = out.teams;
  if (Array.isArray(teams) && teams.every(team => team && typeof team === "object" && !Array.isArray(team))) {
    return { headers: ["team", "n_games", "front_runner_2h_margin", "comeback_2h_margin"], rows: teams.slice(0, 6) as Array<Record<string, unknown>> };
  }
  const sports = out.sports;
  if (sports && typeof sports === "object" && !Array.isArray(sports)) {
    return { headers: ["sport", "n_series_used", "n_move_pairs", "final_hour_movement_share"], rows: Object.entries(sports as Record<string, Record<string, unknown>>).slice(0, 6).map(([sport, values]) => ({ sport, ...values })) };
  }
  return { headers: ["measurement", "published value"], rows: Object.entries(out).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value)).slice(0, 6).map(([measurement, value]) => ({ measurement, "published value": value })) };
}

function value(value: unknown): string {
  return value == null ? "-" : typeof value === "number" ? Number(value.toFixed(6)).toString() : String(value);
}

export function ModuleDetail({ mod, out, insight, subtitle }: { mod: Mod; out: Out; insight: Insight | null; subtitle: string }) {
  const asOf = provenanceDate(mod.as_of);
  const cited = (insight?.cited || []).filter(cite => fact(cite.value));
  const descriptive = out.descriptive_only === true || /descriptive/i.test(insight?.caveat || "");
  const chart = mod.chart_path ? `${base}/img/showcase/${name(mod.chart_path)}` : null;
  const presentation = getPublishedChartPresentation(mod.id);
  const useChartImage = !!chart && presentation.approved;
  const replacement = fallbackData(out);
  const evidence = classifyModuleEvidence(mod.id, mod.status, out);
  const integrityNotices = noticesForModules([mod.id]);
  const source = cited[0]?.path || mod.out_path;
  const sourceHref = artifactUrl(source);
  const envelope: ScoutEnvelope = insight
    ? { status: descriptive ? "descriptive_only" : "ok", prose: insight.headline_insight || "", chips: cited.slice(0, 4).map(cite => ({ value: text(cite.value), label: cite.field, sourceArtifact: cite.path || mod.out_path, asOf: mod.as_of, verdict: "descriptive_only" })) }
    : { status: "no_data", prose: "" };

  return <div className="wrap" style={{ paddingTop: 8 }}>
    <div className="mv-crumbs"><Link href="/analytics/browse">Browse</Link> &rsaquo; {mod.title}</div>
    {descriptive && <div className="mv-banner">Descriptive only - a measured pattern, not a forecast.</div>}
    <div className="mv-head"><div><div className="overline">Analytics module &middot; {asOf}</div><h1 className="serif">{insight?.title || mod.title}</h1>{subtitle && <p className="mv-sub">{subtitle}</p>}</div>{useChartImage && <a className="mv-dl" href={chart} target="_blank" rel="noopener">View full size</a>}</div>
    <DataIntegrityNotice notices={integrityNotices} moduleIds={[mod.id]} />
    <VerdictLegend style={{ margin: "0 0 24px" }} />
    <div className="mv-grid"><div>
      {useChartImage && <Figure source={mod.out_path} asOf={mod.as_of} title={mod.title} verdict="descriptive_only"><img src={chart} alt={`${mod.title} chart`} style={{ width: "100%", height: "auto", display: "block" }} /></Figure>}
      {chart && !useChartImage && <Figure source={mod.out_path} asOf={mod.as_of} title={mod.title} note={presentation.reason} verdict="descriptive_only"><div className="mv-data-figure" data-testid="published-data-figure" role="region" tabIndex={0} aria-label="Published replacement measurements (scrollable table)" data-scroll-region><table><thead><tr>{replacement.headers.map(header => <th key={header}>{header.replaceAll("_", " ")}</th>)}</tr></thead><tbody>{replacement.rows.map((row, index) => <tr key={index}>{replacement.headers.map(header => <td key={header}>{value(row[header])}</td>)}</tr>)}</tbody></table></div></Figure>}
      <ModuleReadingGuide howToRead={insight?.how_to_read} />
      <ModuleEvidence evidence={evidence} moduleId={mod.id} />
      {!chart && evidence.availability === "published" && <div className="mv-nochart mono">This source has no chart. Its cited measurements appear below.</div>}
      {evidence.availability !== "unavailable" && <ScoutNote envelope={envelope} />}
      {insight?.what_it_means && <section className="mv-prose"><h2 className="overline">What it means</h2><p>{insight.what_it_means}</p></section>}
      {insight?.caveat && <section className="mv-caveat"><h2 className="overline">Caveats and confounds</h2><p>{insight.caveat}</p></section>}
    </div><aside className="mv-side"><section className="mv-box"><h2 className="serif">Receipts</h2>
      {cited.length ? <div className="mv-table-scroll" role="region" tabIndex={0} aria-label="Published module receipts (scrollable table)" data-scroll-region><table><caption className="sr-only">Published module receipts</caption><tbody>{cited.map((cite: Cite, index) => <tr key={index}><th scope="row">{cite.field || "value"}</th><td className="tnum">{text(cite.value)}</td></tr>)}</tbody></table></div> : <p className="mono">No cited measurements are published for this module.</p>}
      <p className="mono mv-source">{sourceHref ? <a href={sourceHref} download>{source}</a> : <>{source} (not published)</>}</p>
    </section><section className="mv-box"><h2 className="serif">Continue reading</h2><Link href="/analytics/browse">Back to the catalog</Link><Link href="/analytics/the-loop">Mechanism ledger</Link><Link href={`/analytics/ask/?q=${encodeURIComponent(mod.title)}`}>Ask Scout about this module</Link></section></aside></div>
    <RelatedReading kind="module" id={mod.id} />
    <style>{`.mv-crumbs{font-size:13px;color:var(--ink-3);padding:22px 0 6px}.mv-crumbs a{text-decoration:underline;text-underline-offset:3px}.mv-banner{display:inline-block;margin:8px 0 24px;padding:8px 14px;border:1px solid var(--rule-strong);border-radius:8px;background:var(--paper-tint);font-size:13px}.mv-head{display:flex;justify-content:space-between;align-items:end;gap:20px;border-bottom:1px solid var(--rule-strong);padding-bottom:22px;margin-bottom:30px}.mv-head h1{font-size:clamp(2.2rem,4.6vw,3.2rem);margin:4px 0;font-weight:500}.mv-sub,.mv-prose p,.mv-caveat p,.mv-reading p{color:var(--ink-2);line-height:1.6}.mv-dl,.mv-box a{color:var(--accent)}.mv-grid{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:40px}.mv-nochart,.mv-caveat,.mv-reading,.mv-data-figure{margin:20px 0;padding:18px;border:1px solid var(--rule);border-radius:var(--radius-card);background:var(--paper-tint)}.mv-reading h2{margin-bottom:6px}.mv-prose{margin:24px 0}.mv-box{padding:18px;margin-bottom:20px;border:1px solid var(--rule);border-radius:var(--radius-card);background:var(--paper-raised)}.mv-box h2{font-size:19px;font-weight:500;margin-bottom:12px}.mv-box table,.mv-data-figure table{width:100%;min-width:560px;border-collapse:collapse}.mv-data-figure,.mv-table-scroll{overflow-x:auto}.mv-box td,.mv-box th,.mv-data-figure td,.mv-data-figure th{padding:7px 0;border-bottom:1px solid var(--rule);font-size:13px;text-align:left}.mv-box th,.mv-data-figure th{color:var(--ink-3);font-weight:500}.mv-box td:last-child{text-align:right;overflow-wrap:anywhere}.mv-source{overflow-wrap:anywhere}.mv-box a{display:block;margin-top:9px;font-size:14px}@media(max-width:820px){.mv-grid{grid-template-columns:1fr}.mv-head{align-items:start;flex-direction:column}}`}</style>
  </div>;
}
