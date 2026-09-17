// Authored reading-room answers, shaped from committed artifacts by the server loader.
import { sourceModuleIds } from "./scoutIntegrity";
import { analysisDestinations } from "./analysisDestinations";
import type { AskEntry } from "./askSearch";

export type SourceArtifact = { id: string; artifact: string; asOf: string | null; data: unknown };
export type ExplainerEssay = { slug: string; title: string; cited: string[]; body_md?: string; dek?: string; sourceModuleIds?: string[] };
export type PaperRecord = { slug: string; title: string; date: string; abstract: string; evidence?: { artifact: string }[] };
type SupportUnit = "forecast observations" | "games" | "transitions" | "rows" | "pitches";
type InspectorSupport = { sport: string; unit: SupportUnit; n: number; population?: string };

const SPORT_LABELS: Record<string, string> = { mlb: "MLB", soccer_intl: "International soccer", soccer: "Soccer", nba: "NBA", tennis: "Tennis" };
// First field present wins. Ordered so a row/record count beats a coarser game
// count, and a transition count beats the raw pitch total behind it.
const COUNT_FIELDS: ReadonlyArray<readonly [string, SupportUnit]> = [
  ["n_rows", "forecast observations"],
  ["n_records", "forecast observations"],
  ["n_games_usable", "games"],
  ["n_transitions", "transitions"],
  ["n_pitches_total", "pitches"],
];

function sportLabel(id: string): string { return SPORT_LABELS[id] || id.replace(/_/g, " "); }

function countsIn(sport: string, block: unknown, population?: string): InspectorSupport[] {
  if (!block || typeof block !== "object") return [];
  const record = block as Record<string, unknown>;
  for (const [field, unit] of COUNT_FIELDS) {
    const value = record[field];
    if (typeof value === "number" && Number.isFinite(value)) return [{ sport: sportLabel(sport), unit, n: value, population }];
  }
  return [];
}

/**
 * Reads the published support straight off the artifact the inspector cites, so
 * a regeneration moves the answer without anyone editing a constant here.
 * Three artifact shapes cover every registered inspector: a sports-keyed block,
 * a rows array with its own per-row n, and a single-sport flat artifact.
 */
function supportFrom(artifact: SourceArtifact): InspectorSupport[] {
  if (!artifact.data || typeof artifact.data !== "object") return [];
  const record = artifact.data as Record<string, unknown>;
  const sports = record.sports;
  if (sports && typeof sports === "object") {
    return Object.entries(sports as Record<string, unknown>).flatMap(([sport, block]) => countsIn(sport, block));
  }
  if (Array.isArray(record.rows)) {
    return (record.rows as Record<string, unknown>[]).flatMap(row => typeof row.n === "number" && Number.isFinite(row.n)
      ? [{ sport: sportLabel(String(row.sport || "")), unit: "rows" as const, n: row.n, population: String(row.market || "").split(" (")[0].replace(/_/g, " ") || undefined }]
      : []);
  }
  return countsIn(String(record.sport || ""), record);
}

function supportSentence(support: readonly InspectorSupport[]): string {
  if (!support.length) return "Published support is described in the source artifact.";
  return `Published support: ${support.map(item => `${item.sport}${item.population ? ` ${item.population}` : ""}: ${item.n.toLocaleString("en-US")} ${item.unit}`).join("; ")}.`;
}
function dateFrom(artifact: SourceArtifact): string {
  const data = artifact.data;
  if (data && typeof data === "object" && "as_of" in data && typeof data.as_of === "string" && data.as_of.trim()) return data.as_of;
  return artifact.asOf?.trim() ? artifact.asOf : "date unrecorded";
}
function sourceName(artifact: SourceArtifact): string { return artifact.artifact.replace("webapp/public/data/showcase/", ""); }
function pageVerb(purpose: string): string { return purpose.replace(/^Inspect\b/, "inspects").replace(/^Read\b/, "reads").replace(/^Compare\b/, "compares"); }

const EXACT_COUNT_QUESTIONS = ["exact count", "Compare exact count pitch profiles", "exact count pitch profile", "compare MLB counts 3-0 and 0-2", "compare balls and strikes", "MLB exact count"];
const EXACT_COUNT_SCOPE = " Open the exact-count explorer to select two pre-pitch ball-strike counts and compare their published rates in percentage points. Exact-count n is the pitch cohort size only. The source does not publish exact-count pitch-type, coded-strike, or in-zone rate denominators; class-level denominators must not be substituted. Coded strikes include called, swinging, and foul strikes, not just whiffs. This is a descriptive historical comparison, not a forecast.";

function inspectorAnswers(artifacts: SourceArtifact[]): AskEntry[] {
  const index = new Map(artifacts.map(artifact => [artifact.id, artifact]));
  return analysisDestinations.map(destination => {
    const sources = destination.sourceModuleIds.map(id => index.get(id)).filter((value): value is SourceArtifact => Boolean(value));
    const exactCount = destination.id === "count-context";
    return { q: `What does ${destination.title} measure?`, alt_phrasings: [destination.title, destination.id.replace(/-/g, " "), `${destination.title} inspector`, ...(exactCount ? EXACT_COUNT_QUESTIONS : [])], tags: ["inspector", "reading-room", ...destination.title.toLowerCase().split(" "), destination.id], bucket: "public-inspector", a: { status: "ok", answer: `${destination.title} ${pageVerb(destination.purpose)} Source artifact: ${sources.length ? sources.map(sourceName).join(", ") : "published source artifact not recorded"}. ${supportSentence(sources.flatMap(supportFrom))} Date status: ${sources.map(dateFrom).join(", ") || "date unrecorded"}.${exactCount ? EXACT_COUNT_SCOPE : ""}`, source_artifact: sources[0]?.artifact || "webapp/public/data/showcase/site_manifest.json", source_module_ids: [...destination.sourceModuleIds], as_of: sources[0] ? dateFrom(sources[0]) : "unknown", explore_path: destination.route } };
  });
}

function directAnswer(essay: ExplainerEssay): string { const lead = (essay.dek || (essay.body_md || "").split(/\n+/).find(line => line.trim() && !line.startsWith("#")) || "").replace(/[*_`]/g, "").trim(); const first = lead.split(/(?<=[.!?])\s+/)[0] || ""; return first ? `${first}${/[.!?]$/.test(first) ? "" : "."}` : "Its question is stated in the essay itself."; }
function citedSupport(body: string | undefined): string { const match = body?.match(/\b(?:n\s*=\s*|over\s+)([\d,]+)/i); return match ? `Published support: n=${match[1]}.` : "Published support is described in the cited artifacts."; }
function explainerAnswers(essays: ExplainerEssay[]): AskEntry[] { return essays.map(essay => ({ q: `What does the explainer ${essay.title} cover?`, alt_phrasings: [essay.title, essay.slug.replace(/-/g, " ")], tags: ["explainer", "reading-room", ...essay.title.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)], bucket: "public-explainer", a: { status: "ok", answer: `${essay.title} is a published explainer. ${directAnswer(essay)} Cited artifacts: ${essay.cited.join("; ") || "citations not recorded"}. ${citedSupport(essay.body_md)} Date status: the explainer is a committed snapshot and its cited artifacts carry their own recorded dates.`, source_artifact: "webapp/public/data/explainers/explainers.json", source_module_ids: essay.sourceModuleIds ?? sourceModuleIds(essay.cited), as_of: "unknown", explore_path: `/analytics/explainers/${essay.slug}/` } })); }
function paperAnswers(papers: PaperRecord[]): AskEntry[] { return papers.map(paper => ({ q: `What does the paper ${paper.title} cover?`, alt_phrasings: [paper.title, paper.slug.replace(/-/g, " ")], tags: ["paper", "reading-room", ...paper.title.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)], bucket: "public-paper", a: { status: "ok", answer: `${paper.title} is a published research paper. ${paper.abstract.split(/(?<=[.!?])\s+/)[0]} Source artifacts: ${(paper.evidence || []).map(item => item.artifact).join(", ") || "listed in the paper"}. Date status: ${paper.date}.`, source_artifact: `webapp/public/data/papers/${paper.slug}.json`, source_module_ids: sourceModuleIds((paper.evidence || []).map(item => item.artifact)), as_of: paper.date, explore_path: `/analytics/papers/${paper.slug}/` } })); }

export function buildReadingRoomAnswers(artifacts: SourceArtifact[], essays: ExplainerEssay[], papers: PaperRecord[]): AskEntry[] { return [...inspectorAnswers(artifacts), ...explainerAnswers(essays), ...paperAnswers(papers)]; }
export function isReadingRoomPath(path: string, entries: AskEntry[]): boolean { return entries.some(entry => ["public-inspector", "public-explainer", "public-paper"].includes(entry.bucket) && entry.a.explore_path === path); }
