import { readFileSync } from "node:fs";
import { join } from "node:path";
import { provenanceDate } from "@/lib/analytics/artifactProvenance";
import { selectNovelMeasurement, type NovelMeasurement } from "@/lib/analytics/novelCards";

const DATA = join(process.cwd(), "public", "data", "showcase");
type Row = Record<string, unknown>;

interface IndexEntry {
  stat_name: string;
  abbrev: string;
  module: string;
  source_artifacts?: string[];
}
interface Index { generated_at?: string; stats?: IndexEntry[]; }
export interface NovelCard extends NovelMeasurement {
  id: string;
  title: string;
  abbrev: string;
  sourceArtifacts: string[];
  snapshot: string;
  confoundCount: number;
  estimatorWindows: Array<[string, string]>;
}

const readJson = <T,>(file: string): T => JSON.parse(readFileSync(join(DATA, file), "utf8")) as T;
const asRow = (value: unknown): Row => value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};
const indexGenerated = (value: string): string => {
  const date = provenanceDate(value, "source");
  return date.startsWith("Source as of ") ? `Index generated ${date.slice(13)}` : "Date not published.";
};

export const formatNovelSnapshot = (artifact: Row, indexDate: string): string => {
  if (typeof artifact.as_of === "string") return provenanceDate(artifact.as_of, "source");
  if (typeof artifact.generated_at === "string") return provenanceDate(artifact.generated_at, "snapshot");
  return indexGenerated(indexDate);
};

export function estimatorWindows(artifact: Row): Array<[string, string]> {
  const asOf = asRow(artifact.as_of);
  return Object.entries(asOf)
    .filter(([, value]) => typeof value === "string" && value.length > 0)
    .map(([key, value]) => [key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase()), provenanceDate(value as string, "window")]);
}

/** Reads the committed index and each card artifact for the static export. */
export function getNovelCards(): NovelCard[] {
  const index = readJson<Index>("novel_stats_index.json");
  const stamp = typeof index.generated_at === "string" ? index.generated_at : "";
  return (index.stats || []).map((entry) => {
    const artifact = readJson<Row>(`${entry.module}.json`);
    return {
      id: entry.module,
      title: entry.stat_name,
      abbrev: entry.abbrev,
      sourceArtifacts: entry.source_artifacts || [],
      snapshot: formatNovelSnapshot(artifact, stamp),
      confoundCount: Array.isArray(artifact.declared_confounds) ? artifact.declared_confounds.length : 0,
      estimatorWindows: estimatorWindows(artifact),
      ...selectNovelMeasurement(entry.module, artifact),
    };
  });
}
