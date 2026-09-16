// Authored reading-room answers, shaped from committed artifacts by the server loader.
import { analysisDestinations } from "./analysisDestinations";
import type { AskEntry } from "./askSearch";

export type SourceArtifact = { id: string; artifact: string; asOf: string | null; data: unknown };
export type ExplainerEssay = { slug: string; title: string; cited: string[]; body_md?: string };
export type PaperRecord = { slug: string; title: string; date: string; abstract: string; evidence?: { artifact: string }[] };
type SupportUnit = "forecast observations" | "games" | "transitions" | "cells" | "rows";
type InspectorSupport = { sport: string; unit: SupportUnit; n: number; population?: string };

const INSPECTOR_SUPPORT: Readonly<Record<string, readonly InspectorSupport[]>> = {
  calibration: [{ sport: "MLB", unit: "forecast observations", n: 78986 }, { sport: "International soccer", unit: "forecast observations", n: 9003 }],
  "state-reliability": [{ sport: "MLB", unit: "forecast observations", n: 78986 }, { sport: "International soccer", unit: "forecast observations", n: 9003 }],
  "pitch-sequencing": [{ sport: "MLB", unit: "transitions", n: 512289 }],
  "count-context": [{ sport: "MLB", unit: "rows", n: 693037 }],
  "score-decomposition": [{ sport: "MLB", unit: "forecast observations", n: 78986 }, { sport: "International soccer", unit: "forecast observations", n: 9003 }],
  "observation-dependence": [{ sport: "MLB", unit: "forecast observations", n: 78986 }, { sport: "International soccer", unit: "forecast observations", n: 9003 }],
  "residual-anatomy": [{ sport: "MLB", unit: "forecast observations", n: 78986 }, { sport: "International soccer", unit: "forecast observations", n: 9003 }],
  "blowout-timing": [{ sport: "MLB", unit: "games", n: 178 }, { sport: "International soccer", unit: "games", n: 29 }],
  "state-contrasts": [{ sport: "MLB", population: "from state", unit: "cells", n: 2458 }, { sport: "MLB", population: "to state", unit: "cells", n: 2079 }, { sport: "International soccer", population: "from state", unit: "cells", n: 109 }, { sport: "International soccer", population: "to state", unit: "cells", n: 176 }],
  "cross-sport-comparability": [{ sport: "MLB", population: "moneyline ingame", unit: "rows", n: 78986 }, { sport: "MLB", population: "totals margin", unit: "rows", n: 671 }, { sport: "International soccer", unit: "rows", n: 9003 }, { sport: "NBA", unit: "rows", n: 6371 }, { sport: "Tennis", unit: "rows", n: 55075 }],
};

function supportSentence(support: readonly InspectorSupport[]): string {
  if (!support.length) return "Published support is described in the source artifact.";
  return `Published support: ${support.map(item => `${item.sport}${item.population ? ` ${item.population}` : ""}: ${item.n.toLocaleString("en-US")} ${item.unit}`).join("; ")}.`;
}
function dateFrom(artifact: SourceArtifact): string { if (artifact.asOf) return artifact.asOf; const data = artifact.data; return data && typeof data === "object" && "as_of" in data && typeof data.as_of === "string" ? data.as_of : "date unrecorded"; }
function sourceName(artifact: SourceArtifact): string { return artifact.artifact.replace("webapp/public/data/showcase/", ""); }
function pageVerb(purpose: string): string { return purpose.replace(/^Inspect\b/, "inspects").replace(/^Read\b/, "reads").replace(/^Compare\b/, "compares"); }

function inspectorAnswers(artifacts: SourceArtifact[]): AskEntry[] {
  const index = new Map(artifacts.map(artifact => [artifact.id, artifact]));
  return analysisDestinations.map(destination => {
    const sources = destination.sourceModuleIds.map(id => index.get(id)).filter((value): value is SourceArtifact => Boolean(value));
    return { q: `What does ${destination.title} measure?`, alt_phrasings: [destination.title, destination.id.replace(/-/g, " "), `${destination.title} inspector`], tags: ["inspector", "reading-room", ...destination.title.toLowerCase().split(" "), destination.id], bucket: "public-inspector", a: { status: "ok", answer: `${destination.title} ${pageVerb(destination.purpose)} Source artifact: ${sources.length ? sources.map(sourceName).join(", ") : "published source artifact not recorded"}. ${supportSentence(INSPECTOR_SUPPORT[destination.id] || [])} Date status: ${sources.map(dateFrom).join(", ") || "date unrecorded"}.`, source_artifact: sources[0]?.artifact || "webapp/public/data/showcase/site_manifest.json", as_of: sources[0] ? dateFrom(sources[0]) : "unknown", explore_path: destination.route } };
  });
}

function citedSupport(body: string | undefined): string { const match = body?.match(/\b(?:n\s*=\s*|over\s+)([\d,]+)/i); return match ? `Published support: n=${match[1]}.` : "Published support is described in the cited artifacts."; }
function explainerAnswers(essays: ExplainerEssay[]): AskEntry[] { return essays.map(essay => ({ q: `What does the explainer ${essay.title} cover?`, alt_phrasings: [essay.title, essay.slug.replace(/-/g, " ")], tags: ["explainer", "reading-room", ...essay.title.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)], bucket: "public-explainer", a: { status: "ok", answer: `${essay.title} is a published explainer. It measures and interprets the reading question described in its cited artifacts: ${essay.cited.join("; ") || "citations not recorded"}. ${citedSupport(essay.body_md)} Date status: the explainer is a committed snapshot and its cited artifacts carry their own recorded dates.`, source_artifact: "webapp/public/data/explainers/explainers.json", as_of: "unknown", explore_path: `/analytics/explainers/${essay.slug}/` } })); }
function paperAnswers(papers: PaperRecord[]): AskEntry[] { return papers.map(paper => ({ q: `What does the paper ${paper.title} cover?`, alt_phrasings: [paper.title, paper.slug.replace(/-/g, " ")], tags: ["paper", "reading-room", ...paper.title.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)], bucket: "public-paper", a: { status: "ok", answer: `${paper.title} is a published research paper. ${paper.abstract.split(/(?<=[.!?])\s+/)[0]} Source artifacts: ${(paper.evidence || []).map(item => item.artifact).join(", ") || "listed in the paper"}. Date status: ${paper.date}.`, source_artifact: `webapp/public/data/papers/${paper.slug}.json`, as_of: paper.date, explore_path: `/analytics/papers/${paper.slug}/` } })); }

export function buildReadingRoomAnswers(artifacts: SourceArtifact[], essays: ExplainerEssay[], papers: PaperRecord[]): AskEntry[] { return [...inspectorAnswers(artifacts), ...explainerAnswers(essays), ...paperAnswers(papers)]; }
export function isReadingRoomPath(path: string, entries: AskEntry[]): boolean { return entries.some(entry => ["public-inspector", "public-explainer", "public-paper"].includes(entry.bucket) && entry.a.explore_path === path); }
