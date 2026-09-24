import siteManifest from "@/public/data/showcase/site_manifest.json";

export type DateKind = "source" | "snapshot" | "window" | "published";
export type ObservationWindow = { start: string; end: string };
export type ProvenanceDate = string | ObservationWindow | null | undefined;

type ManifestModule = {
  id: string;
  out_path: string;
};

const publishedArtifacts = new Set([
  ...(siteManifest.modules as ManifestModule[]).flatMap((entry) => [
    `${entry.id}.json`,
    fileName(entry.out_path),
  ]),
  // Staged atlas packs are public sources, but are not site_manifest modules.
  "atlas_nba_manifest.json",
  "atlas_nba_teams_manifest.json",
  "atlas_mlb_batters_manifest.json",
  "atlas_mlb_pitch_manifest.json",
  "atlas_soccer_manifest.json",
  "atlas_tennis_manifest.json",
  "atlas_calibration_manifest.json",
]);

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() || "";
}

function basePath(): string {
  return (process.env.NEXT_PUBLIC_BASE_PATH || "").replace(/\/$/, "");
}

function isoDate(value: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?$/.exec(value);
  if (!match) return null;
  const [year, month, day] = match.slice(1, 4).map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day
    ? value.slice(0, 10)
    : null;
}

function windowDates(value: ProvenanceDate): ObservationWindow | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const start = isoDate(value.start);
  const end = isoDate(value.end);
  return start && end ? { start, end } : null;
}

/** Returns a verified public source URL, or an exported JSON URL for published artifacts. */
export function artifactUrl(source: string | null | undefined, base = basePath()): string | null {
  if (!source) return null;
  if (source === "docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md") {
    return "https://github.com/neeljshah/court-vision/blob/1bfcaf034df3b8639c6b81cd550cbaf27498a229/docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md";
  }
  const name = fileName(source.split(/[?#]/, 1)[0]);
  if (!name || !publishedArtifacts.has(name)) return null;
  return `${base}/data/showcase/${name}`;
}

/** Keeps source dates, artifact generation dates, and observation windows distinct. */
export function describeDate(value: ProvenanceDate, kind: DateKind): string {
  if (kind !== "window") {
    const date = typeof value === "string" ? isoDate(value) : null;
    const labels = { snapshot: "Snapshot generated", source: "Source as of", published: "Published date" };
    return date ? `${labels[kind]} ${date}` : "Date not published.";
  }
  const window = windowDates(value);
  if (window) return `Observation window ${window.start} to ${window.end}`;
  // A published window may be a labelled span ("2024-25 regular season (through 2026-04-12)"); keep it
  // when it names a year and is not a placeholder, otherwise say so.
  const label = typeof value === "string" ? value.trim() : "";
  return labelledWindow(label) ? `Observation window ${label}` : "Date not published.";
}

const PLACEHOLDER_LABEL = /^(published snapshot|snapshot|n\/a|na|none|unknown|tbd|-+)$/i;
function labelledWindow(label: string): boolean {
  // An ISO stamp is a date, never a window; a labelled span must name a year and not be a placeholder.
  return label.length > 0 && label.length <= 120 && isoDate(label) === null && /(19|20)[0-9]{2}/.test(label) && !PLACEHOLDER_LABEL.test(label);
}

/** Compatibility wrapper for older consumers while they adopt describeDate. */
export function provenanceDate(value: ProvenanceDate, kind: DateKind | "observation_window" = "source"): string {
  return describeDate(value, kind === "observation_window" ? "window" : kind);
}

/** Resolves artifact fields before a manifest date that may have mixed origins. */
export function artifactDate(artifact: Record<string, unknown>, fallback: ProvenanceDate): { asOf: ProvenanceDate; dateKind: DateKind } {
  if (typeof artifact.as_of === "string") {
    return { asOf: artifact.as_of, dateKind: labelledWindow(artifact.as_of) ? "window" : "source" };
  }
  if (typeof artifact.generated_at === "string") return { asOf: artifact.generated_at, dateKind: "snapshot" };
  return { asOf: fallback, dateKind: describeDate(fallback, "window") !== "Date not published." ? "window" : "published" };
}
