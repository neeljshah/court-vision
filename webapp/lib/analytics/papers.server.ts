import { existsSync, readdirSync, readFileSync } from "node:fs";
import { findingsIndex } from "./findingsIndex";
import { join } from "node:path";
import { analysisDestinations } from "./analysisDestinations";
import { getResearchAnalyses } from "./researchData";
import { relatedHref, sortPapers, type Paper, type PaperReferences, type PaperRelated } from "./papers";
import { validatePaperEvidence } from "./paperEvidence.server";
import { validatePaper } from "./papers";
import { artifactDate, type DateKind, type ProvenanceDate } from "./artifactProvenance";

type ManifestModule = { id: string; title: string; out_path: string; chart_path: string | null; as_of: string | null };

const root = () => process.cwd();
const fileName = (path: string) => path.split(/[\\/]/).pop() || "";

function manifestModules(): ManifestModule[] {
  try {
    const raw = readFileSync(join(root(), "public", "data", "showcase", "site_manifest.json"), "utf8");
    return (JSON.parse(raw) as { modules?: ManifestModule[] }).modules || [];
  } catch {
    return [];
  }
}

/** Artifact names a paper is allowed to cite: the published manifest plus the insight files. */
export function publishedArtifacts(): Set<string> {
  const names = new Set<string>();
  for (const entry of manifestModules()) {
    names.add(`${entry.id}.json`);
    if (entry.out_path) names.add(fileName(entry.out_path));
  }
  for (const directory of ["showcase", "insights"]) {
    const location = join(root(), "public", "data", directory);
    if (existsSync(location)) {
      for (const entry of readdirSync(location)) if (entry.endsWith(".json")) names.add(entry);
    }
  }
  return names;
}

/** Registered related targets, including every valid paper slug found on disk before filtering. */
export function paperReferences(): PaperReferences {
  const directory = join(root(), "public", "data", "papers");
  const paperIds = new Set<string>();
  if (existsSync(directory)) {
    for (const entry of readdirSync(directory)) {
      if (!entry.endsWith(".json")) continue;
      try {
        const paper = JSON.parse(readFileSync(join(directory, entry), "utf8")) as { slug?: unknown };
        if (typeof paper.slug === "string") paperIds.add(paper.slug);
      } catch { /* malformed files are reported when their own entry is validated */ }
    }
  }
  return {
    analysisIds: new Set(getResearchAnalyses().map(entry => entry.id)),
    findingIds: new Set(findingsIndex.map(entry => entry.slug)),
    moduleIds: new Set(manifestModules().map(entry => entry.id)),
    paperIds,
  };
}

/**
 * Reads every paper in public/data/papers at build time. An invalid file is skipped with a
 * warning naming the file and the reason, so one bad paper never fails the static export.
 */
export function loadPapers(): Paper[] {
  const directory = join(root(), "public", "data", "papers");
  if (!existsSync(directory)) return [];
  const artifacts = publishedArtifacts();
  const references = paperReferences();
  const papers: Paper[] = [];
  for (const entry of readdirSync(directory)) {
    if (!entry.endsWith(".json")) continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(readFileSync(join(directory, entry), "utf8"));
    } catch (error) {
      console.warn(`papers: skipped ${entry} -- unparsable JSON (${String(error)})`);
      continue;
    }
    // The contract (schema, vocabulary, ASCII, related ids) decides whether a paper renders; an
    // unresolved evidence field path only warns here -- scripts/check-paper-evidence.mjs fails the
    // publication check for it, so the site never loses a schema-valid paper over a path typo.
    const contract = validatePaper(parsed, artifacts, references);
    if (contract) { console.warn(`papers: skipped ${entry} -- ${contract}`); continue; }
    const evidence = validatePaperEvidence(parsed, artifacts, references);
    if (evidence) console.warn(`papers: evidence warning ${entry} -- ${evidence}`);
    papers.push(parsed as Paper);
  }
  return sortPapers(papers);
}

type FigureFallback = { headers: string[]; rows: Array<Record<string, unknown>> };
export type PaperFigure = { id: string; title: string; chartSrc: string | null; source: string; asOf: ProvenanceDate; dateKind: DateKind; fallback: FigureFallback };

function figureFallback(value: unknown): FigureFallback {
  const output = value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const teams = output.teams;
  if (Array.isArray(teams) && teams.every(entry => entry && typeof entry === "object" && !Array.isArray(entry))) {
    return { headers: ["team", "n_games", "front_runner_2h_margin", "comeback_2h_margin"], rows: teams.slice(0, 6) as Array<Record<string, unknown>> };
  }
  return {
    headers: ["measurement", "published value"],
    rows: Object.entries(output).filter(([, entry]) => ["string", "number", "boolean"].includes(typeof entry)).slice(0, 6)
      .map(([measurement, entry]) => ({ measurement, "published value": entry })),
  };
}

/** Resolves a figure block's source id to its published chart, or null when the id is unknown. */
export function paperFigure(id: string): PaperFigure | null {
  const found = manifestModules().find(entry => entry.id === id);
  if (!found) return null;
  const base = process.env.NEXT_PUBLIC_BASE_PATH || "";
  let data: unknown = {};
  try { data = JSON.parse(readFileSync(join(root(), "public", "data", "showcase", fileName(found.out_path)), "utf8")); } catch { /* source card remains usable */ }
  const date = artifactDate(data && typeof data === "object" && !Array.isArray(data) ? data as Record<string, unknown> : {}, found.as_of);
  return {
    id: found.id,
    title: found.title,
    chartSrc: found.chart_path ? `${base}/img/showcase/${fileName(found.chart_path)}` : null,
    source: found.out_path || `${found.id}.json`,
    asOf: date.asOf,
    dateKind: date.dateKind,
    fallback: figureFallback(data),
  };
}

export type ResolvedRelated = { kind: PaperRelated["kind"]; id: string; href: string; title: string };

/** Titles related links through the inspector registry, the research index, the manifest and other papers. */
export function resolveRelated(links: PaperRelated[], papers?: Paper[]): ResolvedRelated[] {
  const inspectors = new Map(analysisDestinations.map(entry => [entry.id, entry.title]));
  const analyses = new Map(getResearchAnalyses().map(entry => [entry.id, entry.title]));
  const sources = new Map(manifestModules().map(entry => [entry.id, entry.title]));
  const others = new Map((papers || loadPapers()).map(entry => [entry.slug, entry.title]));
  const findings = new Map(findingsIndex.map(entry => [entry.slug, entry.title]));
  const titleFor = (link: PaperRelated) =>
    (link.kind === "inspector" ? inspectors.get(link.id)
      : link.kind === "analysis" ? analyses.get(link.id)
        : link.kind === "module" ? sources.get(link.id)
          : link.kind === "finding" ? findings.get(link.id)
            : others.get(link.id)) || link.id.replace(/[-_]/g, " ");
  return links.map(link => ({ kind: link.kind, id: link.id, href: relatedHref(link), title: titleFor(link) }));
}
