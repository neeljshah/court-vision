import { getResearchAnalyses } from "./researchData";
import type { ResearchAnalysis } from "./researchTypes";

export type ModuleAvailability = "published" | "partial" | "unavailable";
export type CoverageRow = { population: string; status: string; reason?: string; nGamesTotal?: number; nBucketsUsable?: number };
export type ModuleEvidence = {
  availability: ModuleAvailability;
  headline?: string;
  missingInputs: string[];
  coverage: CoverageRow[];
  analyses: Array<{ id: string; title: string }>;
};

type Artifact = Record<string, unknown>;
const unavailable = /^(not_buildable|unavailable|not_available|no_data)$/i;
const partial = /^partial$/i;
const words = (key: string) => key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
const text = (value: unknown) => typeof value === "string" && value.trim() ? value.trim() : undefined;

export function classifyModuleEvidence(
  id: string,
  manifestStatus: string | undefined,
  artifact: Artifact,
  research: ResearchAnalysis[] = getResearchAnalyses(),
): ModuleEvidence {
  const artifactStatus = text(artifact.status);
  const status = artifactStatus || manifestStatus || "ok";
  const availability: ModuleAvailability = unavailable.test(status) ? "unavailable" : partial.test(status) || partial.test(manifestStatus || "") ? "partial" : "published";
  const reason = text(artifact.why) || text(artifact.reason);
  const missingInputs = Object.entries(artifact)
    .filter(([key, value]) => /(?:source_found|source_available|has_.*source)$/i.test(key) && !value)
    .map(([key]) => words(key));
  const sports = artifact.sports;
  const coverage: CoverageRow[] = sports && typeof sports === "object" && !Array.isArray(sports)
    ? Object.entries(sports as Record<string, Artifact>).map(([population, row]) => ({
      population: population.toUpperCase(), status: text(row.status) || "unknown", reason: text(row.reason),
      nGamesTotal: typeof row.n_games_total === "number" ? row.n_games_total : undefined,
      nBucketsUsable: typeof row.n_buckets_usable === "number" ? row.n_buckets_usable : undefined,
    })) : [];
  const headline = availability === "unavailable"
    ? `This measurement cannot be published from the committed inputs. ${reason || "The artifact records no buildable evidence."}`
    : availability === "partial" ? reason || "The committed artifact is partial; only its published coverage is shown here." : undefined;
  return { availability, headline, missingInputs, coverage, analyses: research.filter(a => a.source === id).map(a => ({ id: a.id, title: a.title })) };
}
