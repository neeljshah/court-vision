// Research papers -- pure types, validation and reading helpers. No node:fs here, so a
// "use client" index component can import it; the loader lives in papers.server.ts.
// The vocabulary guard is the same expression scripts/check-analytics-copy.mjs applies to
// source and data, kept literal so the two cannot drift apart.
const FORBIDDEN = /(?<![A-Za-z0-9_])(edge|edges|bet|bets|betting|bettor|bettors|bookmaker|bookmakers|sportsbook|profit|profits|profitable|roi|wager|wagers|wagering|bankroll|bankrolls|payout|payouts|odds boost|financial returns?|betting returns?|dollar)(?![A-Za-z0-9])/gi;

import { analysisDestinations } from "./analysisDestinations";

export type PaperSport = "all" | "nba" | "mlb" | "soccer_intl" | "tennis";
export type PaperRelatedKind = "inspector" | "analysis" | "module" | "paper" | "finding";

export type PaperBlock =
  | { type: "p"; text: string }
  | { type: "list"; items: string[] }
  | { type: "table"; caption: string; columns: string[]; rows: string[][]; note?: string }
  | { type: "figure"; module: string; caption: string }
  | { type: "callout"; label: string; text: string }
  | { type: "math"; text: string };

export type PaperSection = { id: string; heading: string; blocks: PaperBlock[] };
export type PaperEvidencePath = "showcase" | "insights";
export type PaperDateMeaning = "snapshot" | "window" | "not-published";
export type PaperEvidence = {
  artifact: string; module: string; asOf: string | null; fields: string[];
  path?: PaperEvidencePath; dateMeaning?: PaperDateMeaning;
};
export type PaperRelated = { kind: PaperRelatedKind; id: string };
export type PaperReferences = {
  analysisIds?: ReadonlySet<string>; findingIds?: ReadonlySet<string>; paperIds?: ReadonlySet<string>;
};

export type Paper = {
  slug: string; title: string; subtitle: string; authors: string[]; date: string;
  sport: PaperSport; keywords: string[]; abstract: string;
  sections: PaperSection[]; evidence: PaperEvidence[]; limitations: string[]; related: PaperRelated[];
};

const SPORTS = new Set<string>(["all", "nba", "mlb", "soccer_intl", "tennis"]);
const RELATED_KINDS = new Set<string>(["inspector", "analysis", "module", "paper", "finding"]);
const BLOCK_TYPES = new Set<string>(["p", "list", "table", "figure", "callout", "math"]);
const EVIDENCE_PATHS = new Set<string>(["showcase", "insights"]);
const DATE_MEANINGS = new Set<string>(["snapshot", "window", "not-published"]);
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const PRINTABLE_ASCII = /^[\x20-\x7E\n\t]*$/;

export const SPORT_LABELS: Record<PaperSport, string> = {
  all: "Cross-sport", nba: "NBA", mlb: "MLB", soccer_intl: "Soccer", tennis: "Tennis",
};

type Bag = Record<string, unknown>;
const bag = (value: unknown): Bag | null =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Bag) : null;
const filled = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.length > 0 && value.every(filled);

function blockReason(block: unknown, where: string): string | null {
  const item = bag(block);
  if (!item) return `${where} is not an object`;
  const kind = item.type;
  if (typeof kind !== "string" || !BLOCK_TYPES.has(kind)) return `${where} has unknown block type ${String(kind)}`;
  if (kind === "p" || kind === "math") return filled(item.text) ? null : `${where} (${kind}) has no text`;
  if (kind === "callout") return filled(item.label) && filled(item.text) ? null : `${where} (callout) needs a label and text`;
  if (kind === "list") return strings(item.items) ? null : `${where} (list) has no items`;
  if (kind === "figure") return filled(item.module) && filled(item.caption) ? null : `${where} (figure) needs a source id and a caption`;
  if (!filled(item.caption) || !strings(item.columns)) return `${where} (table) needs a caption and columns`;
  if (!Array.isArray(item.rows) || item.rows.length === 0) return `${where} (table) has no rows`;
  const width = item.columns.length;
  const ragged = item.rows.some(row => !Array.isArray(row) || row.length !== width || !row.every(cell => typeof cell === "string"));
  return ragged ? `${where} (table) has a row that does not match its ${width} columns` : null;
}

function sectionReason(section: unknown, index: number): string | null {
  const item = bag(section);
  const where = `sections[${index}]`;
  if (!item) return `${where} is not an object`;
  if (!filled(item.id) || !filled(item.heading)) return `${where} needs an id and a heading`;
  if (!Array.isArray(item.blocks) || item.blocks.length === 0) return `${where} has no blocks`;
  for (let position = 0; position < item.blocks.length; position += 1) {
    const reason = blockReason(item.blocks[position], `${where}.blocks[${position}]`);
    if (reason) return reason;
  }
  return null;
}

function evidenceReason(entry: unknown, index: number, artifacts: ReadonlySet<string>): string | null {
  const item = bag(entry);
  const where = `evidence[${index}]`;
  if (!item) return `${where} is not an object`;
  if (!filled(item.artifact) || !filled(item.module)) return `${where} needs an artifact and a source id`;
  if (!strings(item.fields)) return `${where} needs at least one field path`;
  if (item.asOf !== null && !filled(item.asOf)) return `${where} needs an asOf date or null`;
  if (item.path !== undefined && (typeof item.path !== "string" || !EVIDENCE_PATHS.has(item.path))) return `${where} path must be showcase or insights`;
  if (item.dateMeaning !== undefined && (typeof item.dateMeaning !== "string" || !DATE_MEANINGS.has(item.dateMeaning))) return `${where} dateMeaning is not recognized`;
  return artifacts.has(item.artifact) ? null : `${where} names ${item.artifact}, which is not a published artifact`;
}

/** Every string the paper renders, used for the ASCII, vocabulary and word-count passes. */
export function paperStrings(value: unknown, into: string[] = []): string[] {
  if (typeof value === "string") into.push(value);
  else if (Array.isArray(value)) value.forEach(entry => paperStrings(entry, into));
  else if (value && typeof value === "object") Object.values(value as Bag).forEach(entry => paperStrings(entry, into));
  return into;
}

/** Returns null when the value is a valid paper, otherwise the reason it is excluded. */
export function validatePaper(value: unknown, artifacts: ReadonlySet<string>, references?: PaperReferences): string | null {
  const item = bag(value);
  if (!item) return "not a JSON object";
  if (!filled(item.slug) || !SLUG.test(item.slug)) return "slug must be lower-case kebab-case";
  for (const key of ["title", "subtitle", "abstract"]) if (!filled(item[key])) return `${key} is missing`;
  if (!strings(item.authors)) return "authors must be a non-empty list of names";
  if (!filled(item.date) || !ISO_DATE.test(item.date)) return "date must be YYYY-MM-DD";
  if (typeof item.sport !== "string" || !SPORTS.has(item.sport)) return `sport ${String(item.sport)} is not a known sport`;
  if (!strings(item.keywords)) return "keywords must be a non-empty list";
  if (!strings(item.limitations)) return "limitations must be a non-empty list";
  if (!Array.isArray(item.sections) || item.sections.length === 0) return "sections is empty";
  const sectionIds = new Set<string>();
  for (let index = 0; index < item.sections.length; index += 1) {
    const reason = sectionReason(item.sections[index], index);
    if (reason) return reason;
    const section = item.sections[index] as Bag;
    if (sectionIds.has(section.id as string)) return `duplicate section id ${section.id}`;
    sectionIds.add(section.id as string);
  }
  if (!Array.isArray(item.evidence) || item.evidence.length === 0) return "evidence is empty";
  for (let index = 0; index < item.evidence.length; index += 1) {
    const reason = evidenceReason(item.evidence[index], index, artifacts);
    if (reason) return reason;
  }
  if (!Array.isArray(item.related)) return "related must be a list";
  for (const link of item.related) {
    const target = bag(link);
    if (!target || typeof target.kind !== "string" || !RELATED_KINDS.has(target.kind) || !filled(target.id)) {
      return "related entries need a known kind and an id";
    }
    if (target.kind === "module" && !artifacts.has(`${target.id}.json`)) return `related module ${target.id} has no published module page`;
    if (target.kind === "inspector" && !analysisDestinations.some(entry => entry.id === target.id)) return `related inspector ${target.id} is not registered`;
    if (target.kind === "analysis" && references?.analysisIds && !references.analysisIds.has(target.id)) return `related analysis ${target.id} is not registered`;
    if (target.kind === "finding" && references?.findingIds && !references.findingIds.has(target.id)) return `related finding ${target.id} is not registered`;
    if (target.kind === "paper" && references?.paperIds && !references.paperIds.has(target.id)) return `related paper ${target.id} is not published`;
  }
  for (const text of paperStrings(item)) {
    if (!PRINTABLE_ASCII.test(text)) return `non-ASCII text in ${JSON.stringify(text.slice(0, 40))}`;
    FORBIDDEN.lastIndex = 0;
    const match = FORBIDDEN.exec(text);
    if (match) return `prohibited vocabulary ${JSON.stringify(match[0])}`;
  }
  return null;
}

export function sortPapers(papers: Paper[]): Paper[] {
  return [...papers].sort((left, right) => right.date.localeCompare(left.date) || left.title.localeCompare(right.title));
}

function blockText(block: PaperBlock): string {
  if (block.type === "list") return block.items.join(" ");
  if (block.type === "table") return [block.caption, ...block.columns, ...block.rows.flat(), block.note || ""].join(" ");
  if (block.type === "figure") return block.caption;
  return block.text;
}

export function paperWordCount(paper: Paper): number {
  const text = [paper.abstract, ...paper.sections.flatMap(section => [section.heading, ...section.blocks.map(blockText)])].join(" ");
  return text.split(/\s+/).filter(Boolean).length;
}

/** Reading time at 220 words per minute, never rounded below one minute. */
export function readingMinutes(paper: Paper): number {
  return Math.max(1, Math.round(paperWordCount(paper) / 220));
}

export function excerpt(text: string, limit = 220): string {
  if (text.length <= limit) return text;
  const cut = text.slice(0, limit);
  return `${cut.slice(0, cut.lastIndexOf(" ")).trimEnd()}...`;
}

export function paperKeywords(papers: Paper[]): string[] {
  return [...new Set(papers.flatMap(paper => paper.keywords))].sort((left, right) => left.localeCompare(right));
}

export function paperSports(papers: Paper[]): PaperSport[] {
  const order: PaperSport[] = ["all", "nba", "mlb", "soccer_intl", "tennis"];
  const present = new Set(papers.map(paper => paper.sport));
  return order.filter(sport => present.has(sport));
}

export function filterPapers(papers: Paper[], sport: string, keyword: string): Paper[] {
  return papers.filter(paper => (sport === "any" || paper.sport === sport) && (keyword === "any" || paper.keywords.includes(keyword)));
}

export function relatedHref(link: PaperRelated): string {
  if (link.kind === "inspector") {
    const destination = analysisDestinations.find(entry => entry.id === link.id);
    return destination ? `${destination.route}/` : `/analytics/papers/${link.id}/`;
  }
  if (link.kind === "analysis") return `/analytics/research/${link.id}/`;
  if (link.kind === "module") return `/analytics/m/${link.id}/`;
  if (link.kind === "finding") return `/analytics/findings/${link.id}/`;
  return `/analytics/papers/${link.id}/`;
}

export function paperHref(slug: string): string {
  return `/analytics/papers/${slug}/`;
}
