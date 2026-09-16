// Authored reading-room answers, shaped from committed artifacts by the server loader.
import { analysisDestinations } from "./analysisDestinations";
import type { AskEntry } from "./askSearch";

export type SourceArtifact = { id: string; artifact: string; asOf: string | null; data: unknown };
export type ExplainerEssay = { slug: string; title: string; cited: string[]; body_md?: string };
export type PaperRecord = { slug: string; title: string; date: string; abstract: string; evidence?: { artifact: string }[] };

function supportFrom(value: unknown): number | null {
  if (Array.isArray(value)) for (const item of value) { const support = supportFrom(item); if (support !== null) return support; }
  else if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) if ((key === "n" || key === "n_rows" || key === "n_records" || key === "n_pitches_total") && typeof item === "number" && Number.isFinite(item)) return item;
    for (const item of Object.values(value)) { const support = supportFrom(item); if (support !== null) return support; }
  }
  return null;
}
function dateFrom(artifact: SourceArtifact): string { if (artifact.asOf) return artifact.asOf; const data = artifact.data; return data && typeof data === "object" && "as_of" in data && typeof data.as_of === "string" ? data.as_of : "date unrecorded"; }
function sourceName(artifact: SourceArtifact): string { return artifact.artifact.replace("webapp/public/data/showcase/", ""); }
function pageVerb(purpose: string): string { return purpose.replace(/^Inspect\b/, "inspects").replace(/^Read\b/, "reads").replace(/^Compare\b/, "compares"); }

function inspectorAnswers(artifacts: SourceArtifact[]): AskEntry[] {
  const index = new Map(artifacts.map(artifact => [artifact.id, artifact]));
  return analysisDestinations.map(destination => {
    const sources = destination.sourceModuleIds.map(id => index.get(id)).filter((value): value is SourceArtifact => Boolean(value));
    const support = sources.map(source => supportFrom(source.data)).find((value): value is number => value !== null);
    return { q: `What does ${destination.title} measure?`, alt_phrasings: [destination.title, destination.id.replace(/-/g, " "), `${destination.title} inspector`], tags: ["inspector", "reading-room", ...destination.title.toLowerCase().split(" "), destination.id], bucket: "public-inspector", a: { status: "ok", answer: `${destination.title} ${pageVerb(destination.purpose)} Source artifact: ${sources.length ? sources.map(sourceName).join(", ") : "published source artifact not recorded"}. ${support === undefined ? "Published support is described in the source artifact." : `Published support: n=${support.toLocaleString("en-US")}.`} Date status: ${sources.map(dateFrom).join(", ") || "date unrecorded"}.`, source_artifact: sources[0]?.artifact || "webapp/public/data/showcase/site_manifest.json", as_of: sources[0] ? dateFrom(sources[0]) : "unknown", explore_path: destination.route } };
  });
}

function citedSupport(body: string | undefined): string { const match = body?.match(/\b(?:n\s*=\s*|over\s+)([\d,]+)/i); return match ? `Published support: n=${match[1]}.` : "Published support is described in the cited artifacts."; }
function explainerAnswers(essays: ExplainerEssay[]): AskEntry[] { return essays.map(essay => ({ q: `What does the explainer ${essay.title} cover?`, alt_phrasings: [essay.title, essay.slug.replace(/-/g, " ")], tags: ["explainer", "reading-room", ...essay.title.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)], bucket: "public-explainer", a: { status: "ok", answer: `${essay.title} is a published explainer. It measures and interprets the reading question described in its cited artifacts: ${essay.cited.join("; ") || "citations not recorded"}. ${citedSupport(essay.body_md)} Date status: the explainer is a committed snapshot and its cited artifacts carry their own recorded dates.`, source_artifact: "webapp/public/data/explainers/explainers.json", as_of: "unknown", explore_path: `/analytics/explainers/${essay.slug}/` } })); }
function paperAnswers(papers: PaperRecord[]): AskEntry[] { return papers.map(paper => ({ q: `What does the paper ${paper.title} cover?`, alt_phrasings: [paper.title, paper.slug.replace(/-/g, " ")], tags: ["paper", "reading-room", ...paper.title.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)], bucket: "public-paper", a: { status: "ok", answer: `${paper.title} is a published research paper. It measures ${paper.abstract} Source artifacts: ${(paper.evidence || []).map(item => item.artifact).join(", ") || "listed in the paper"}. Date status: ${paper.date}.`, source_artifact: `webapp/public/data/papers/${paper.slug}.json`, as_of: paper.date, explore_path: `/analytics/papers/${paper.slug}/` } })); }

export function buildReadingRoomAnswers(artifacts: SourceArtifact[], essays: ExplainerEssay[], papers: PaperRecord[]): AskEntry[] { return [...inspectorAnswers(artifacts), ...explainerAnswers(essays), ...paperAnswers(papers)]; }
export function isReadingRoomPath(path: string, entries: AskEntry[]): boolean { return entries.some(entry => ["public-inspector", "public-explainer", "public-paper"].includes(entry.bucket) && entry.a.explore_path === path); }
