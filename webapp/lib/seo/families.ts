// lib/seo/families.ts -- one title + description generator per dynamic page family, built from
// the page's own data (name, pack, metric, claim, packet verdict, as-of). Pure: the page files
// read the artifacts and pass plain values in, so each generator has a unit test
// (lib/seo/__tests__/families.test.ts). Every result goes through pageMeta (canonical, og, twitter,
// description under 160 characters). Descriptive exhibits say "descriptive" in the description.
// Calibration language only; no figure is retyped here beyond an as-of date and a row index.
import type { Metadata } from "next";
import { humanizeMatchup } from "@/lib/betdesc";
import { paperDetailHref } from "@/lib/paperLinks";
import { canonicalUrl, fitDescription, pageMeta, verdictLabel, type MetaExtra } from "./meta";

const SPORT: Record<string, string> = { all: "Cross-sport", nba: "NBA", mlb: "MLB", soccer: "Soccer", soccer_intl: "Soccer", tennis: "Tennis" };
export const sportLabel = (s?: string | null): string => (s && SPORT[s]) || (s ? s.toUpperCase() : "Multi-sport");
const day = (d?: string | null): string | null => (d && /^\d{4}-\d{2}-\d{2}/.test(d) ? d.slice(0, 10) : d?.trim() || null);
const asOf = (d?: string | null): string => (day(d) ? ` As of ${day(d)}.` : "");

export type EntityInput = { pack: string; slug: string; name: string; packLabel: string; sport: string; asOf?: string | null };
/** /analytics/players/<pack>/<slug>/ -- an entity card: descriptive, measured rates, never a projection. */
export function entityMeta(e: EntityInput): Metadata {
  return pageMeta(`/analytics/players/${e.pack}/${e.slug}/`, {
    title: `${e.name} -- ${e.packLabel}`,
    description: fitDescription(`Descriptive reference card for ${e.name} (${e.packLabel}, ${e.sport}): measured historical rates from the published pack, not a prediction.`, asOf(e.asOf)),
  });
}

export type ModuleInput = { id: string; title: string; summary?: string | null; status?: string | null; asOf?: string | null; descriptive?: boolean };
/** /analytics/m/<id>/ -- a published analytics module. */
export function moduleMeta(m: ModuleInput): Metadata {
  const raw = (m.summary || "").replace(/\s+/g, " ").trim();
  const flag = /^descriptive[ _-]?only\.?$/i.test(raw); // a one_line that is only the flag, not a summary
  const summary = flag ? "" : raw;
  const lead = m.descriptive || flag ? "Descriptive analytics module" : "Analytics module";
  const body = summary ? `${lead}: ${summary}` : `${lead} ${m.title}: measured values with their source artifact, status ${m.status || "not published"}.`;
  return pageMeta(`/analytics/m/${m.id}/`, { title: m.title, description: fitDescription(body, asOf(m.asOf)) });
}

export type ResearchInput = { id: string; title: string; description: string; novelty?: string | null; asOf?: string | null };
/** /analytics/research/<id>/ -- a derived analysis (always descriptive). */
export function researchMeta(r: ResearchInput): Metadata {
  const kind = (r.novelty || "derived analysis").toLowerCase();
  return pageMeta(`/analytics/research/${r.id}/`, { title: r.title, description: fitDescription(r.description, ` Descriptive ${kind}.${asOf(r.asOf)}`) });
}

export type PaperInput = { slug: string; title: string; abstract: string; date: string; sport: string };
/** /analytics/papers/<slug>/ -- a research paper; the abstract leads, the sport and date close. */
export function paperMeta(p: PaperInput): Metadata {
  return pageMeta(`/analytics/papers/${p.slug}/`, { title: p.title, description: fitDescription(p.abstract, ` ${sportLabel(p.sport)} research paper, ${p.date}.`), type: "article" });
}

export type ClaimInput = { slug: string; title: string; lede?: string | null; claim?: string | null; bucket?: string | null; status?: string | null };
/** /evidence/<claim>/ -- one evidence claim: its short title, then the lede (else the index teaser), then its bucket. */
export function claimMeta(c: ClaimInput): Metadata {
  const short = c.title.split(" -- ")[0].trim();
  const body = (c.lede || c.claim || "").trim() || "Evidence claim.";
  const prefix = c.status === "VALIDATION_PENDING" ? "Validation pending. " : "";
  return pageMeta(`/evidence/${c.slug}/`, { title: `Evidence / ${c.title}`, description: fitDescription(`${prefix}${short}: ${body}`, c.bucket ? ` (${c.bucket}.)` : "") });
}

export type FillInput = {
  /** The once-encoded fill id (components/paper_pm/paperIds fillParam) = the exported directory name. */
  param: string; sport: string; gameId?: string | null; matchup?: string | null; side?: string | null; ts?: string | null;
  book?: string | null; marketType?: string | null; status?: string | null; stakeUnits?: number | null;
};
/** /paper/<fill>/ -- one forward paper fill; the canonical is the double-encoded href (lib/paperLinks). */
export function fillMeta(f: FillInput): Metadata {
  const game = humanizeMatchup(f.gameId) || humanizeMatchup(f.matchup) || "matchup not published";
  const when = f.ts ? f.ts.slice(0, 19).replace("T", " ") + "Z" : "time not published";
  const side = f.side || "side not published";
  const units = typeof f.stakeUnits === "number" ? `, ${f.stakeUnits} units` : "";
  return pageMeta(paperDetailHref(f.param), {
    title: `Paper fill: ${game}, ${side}, ${when}`,
    description: fitDescription(`${sportLabel(f.sport)} paper fill on ${game}: side ${side}, ${f.marketType || "market not published"} at ${f.book || "venue not published"}, ${when}${units}, status ${f.status || "not published"}.`, " Calibration record; paper units only."),
  });
}

export type ReceiptInput = { index: number; sportMarket: string; checkpoint: string; verdict: string; src?: string | null };
/** /receipts/<i>/ -- one ledger row, named by its market, checkpoint and packet verdict. */
export function receiptMeta(r: ReceiptInput): Metadata {
  const source = (r.src || "").split("/").pop() || "the receipts ledger";
  return pageMeta(`/receipts/${r.index}/`, {
    title: `Receipt ${r.index}: ${r.sportMarket} at ${r.checkpoint}`,
    description: fitDescription(`Ledger row ${r.index}: ${r.sportMarket} at the ${r.checkpoint} checkpoint, verdict ${verdictLabel(r.verdict)}.`, ` Descriptive model-vs-market calibration; source ${source}.`),
  });
}

export type GameInput = { sport: string; gameId: string; home?: string | null; away?: string | null; tipoff?: string | null; asOf?: string | null };
/** /games/<sport>/<id>/ -- a snapshot game page; team names from the baked slate when it has them. */
export function gameMeta(g: GameInput): Metadata {
  const matchup = g.home && g.away ? `${g.away} @ ${g.home}` : humanizeMatchup(g.gameId) || g.gameId;
  const when = day(g.tipoff) ? ` on ${day(g.tipoff)}` : "";
  return pageMeta(`/games/${g.sport}/${g.gameId}/`, {
    title: `${matchup} -- ${sportLabel(g.sport)} game`,
    description: fitDescription(`${matchup}, ${sportLabel(g.sport)}${when}: pregame probability, market surface and in-game calibration.`, ` Paper units only.${asOf(g.asOf)}`),
  });
}

export type ExplainerInput = { slug: string; title: string; dek: string };
/** /analytics/explainers/<slug>/ -- a long-form explainer; the dek is the description. */
export function explainerMeta(e: ExplainerInput): Metadata {
  return pageMeta(`/analytics/explainers/${e.slug}/`, { title: e.title, description: `Explainer: ${e.dek}`, type: "article" });
}

export type FindingInput = { slug: string; title: string; dek: string; verdicts: string[]; asOf?: string | null };
/** /analytics/findings/<slug>/ -- a finding: its dek, its packet verdict (or "descriptive"), its as-of. */
export function findingPageMeta(f: FindingInput, extra: MetaExtra = {}): Metadata {
  const verdict = f.verdicts.length ? ` Verdict: ${f.verdicts.map(verdictLabel).join(", ")}.` : " Descriptive exhibit; no packet verdict.";
  return pageMeta(`/analytics/findings/${f.slug}/`, { title: f.title, description: fitDescription(f.dek, `${verdict}${asOf(f.asOf)}`) }, extra);
}

/** A retired route's stub: noindex, canonical on the destination, a description naming both. */
export function stubMeta(from: string, to: string, label: string): Metadata {
  return pageMeta(from, { title: "Page moved", description: `The page ${from} moved to ${label} (${to}).`, noindex: true, canonical: canonicalUrl(to) });
}
