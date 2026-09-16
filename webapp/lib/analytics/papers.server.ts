import { existsSync, readdirSync, readFileSync } from "node:fs";
import { findingsIndex } from "./findingsIndex";
import { join } from "node:path";
import { analysisDestinations } from "./analysisDestinations";
import { getResearchAnalyses } from "./researchData";
import { relatedHref, sortPapers, validatePaper, type Paper, type PaperRelated } from "./papers";

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
  const insights = join(root(), "public", "data", "insights");
  if (existsSync(insights)) {
    for (const entry of readdirSync(insights)) if (entry.endsWith(".json")) names.add(entry);
  }
  return names;
}

/**
 * Reads every paper in public/data/papers at build time. An invalid file is skipped with a
 * warning naming the file and the reason, so one bad paper never fails the static export.
 */
export function loadPapers(): Paper[] {
  const directory = join(root(), "public", "data", "papers");
  if (!existsSync(directory)) return [];
  const artifacts = publishedArtifacts();
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
    const reason = validatePaper(parsed, artifacts);
    if (reason) console.warn(`papers: skipped ${entry} -- ${reason}`);
    else papers.push(parsed as Paper);
  }
  return sortPapers(papers);
}

export type PaperFigure = { id: string; title: string; chartSrc: string | null; source: string; asOf: string };

/** Resolves a figure block's source id to its published chart, or null when the id is unknown. */
export function paperFigure(id: string): PaperFigure | null {
  const found = manifestModules().find(entry => entry.id === id);
  if (!found) return null;
  const base = process.env.NEXT_PUBLIC_BASE_PATH || "";
  return {
    id: found.id,
    title: found.title,
    chartSrc: found.chart_path ? `${base}/img/showcase/${fileName(found.chart_path)}` : null,
    source: found.out_path || `${found.id}.json`,
    asOf: found.as_of || "",
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
