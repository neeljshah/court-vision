import { field as f, snapshot } from "./labHelpers";
import type { LabRow } from "./labTypes";
import type { ResearchAnalysis, ResearchReference } from "./researchTypes";

type Surface = "hard" | "clay" | "grass";
export type TennisWindowAtlasEntry = {
  entity: string;
  key_numbers: Record<string, unknown>;
  floors?: string;
  as_of?: string;
  status?: string;
};
export type TennisWindowAtlas = { generated_at?: string; entries: TennisWindowAtlasEntry[] };

const SURFACES: Array<{ key: Surface; label: string }> = [
  { key: "hard", label: "Hard-court" },
  { key: "clay", label: "Clay-court" },
  { key: "grass", label: "Grass-court" },
];
const REFERENCES: ResearchReference[] = [{
  title: "Published tennis surface method",
  url: "https://github.com/neeljshah/court-vision/blob/master/scripts/platformkit/intel_validation/tennis_surface_context_claims.py",
}];
const rate = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;

const INDEPENDENT_WINDOWS = "per metric, career+recent_form independently; below floor shows n/a";

function eligible(entry: TennisWindowAtlasEntry, surface: Surface): boolean {
  const floor = entry.floors || "";
  const exactFloor = new RegExp(`(?:^| \\| )${surface}_wr: ${surface}_n>=30(?!\\d)(?: \\| | \\()`);
  const atpName = entry.entity.endsWith(" (ATP)") ? entry.entity.slice(0, -6).trim() : "";
  return atpName.length > 0 && exactFloor.test(floor) && floor.includes(INDEPENDENT_WINDOWS);
}

function rows(entries: TennisWindowAtlasEntry[], surface: Surface): LabRow[] {
  const careerKey = `${surface}_wr_career`;
  const recentKey = `${surface}_wr_recent`;
  return entries.flatMap((entry, index) => {
    const career = rate(entry.key_numbers[careerKey]);
    const recent = rate(entry.key_numbers[recentKey]);
    if (!eligible(entry, surface) || career === null || recent === null) return [];
    return [{
      id: `${surface}-${index}`,
      label: entry.entity,
      group: `${surface[0].toUpperCase()}${surface.slice(1)} paired window`,
      values: { recent_minus_career: recent - career, recent_rate: recent, career_rate: career },
      note: `Source floor: ${entry.floors}. Both operands clear independent source windows; exact match counts are not published. Source status: ${entry.status || "unrecorded"}.`,
    }];
  });
}

function commonAsOf(entries: TennisWindowAtlasEntry[]): string | undefined {
  if (!entries.length || entries.some(entry => typeof entry.as_of !== "string" || !/^\d{4}-\d{2}-\d{2}T/.test(entry.as_of) || !Number.isFinite(Date.parse(entry.as_of)))) return undefined;
  const dates = new Set(entries.map(entry => entry.as_of as string));
  return dates.size === 1 ? [...dates][0] : undefined;
}

export function buildTennisWindowResearch(atlas: TennisWindowAtlas): ResearchAnalysis[] {
  return SURFACES.map(({ key, label }) => {
    const paired = rows(atlas.entries, key);
    const included = atlas.entries.filter(entry => paired.some(row => row.label === entry.entity));
    const asOf = commonAsOf(included);
    return {
      id: `tennis-${key}-recent-career-shift`,
      title: `${label} recent-versus-career win rate`,
      sport: "tennis",
      category: "Surface windows",
      source: "atlas_tennis_manifest",
      description: `Compare each published ATP player's ${label.toLowerCase()} win rate since 2023 with the overlapping source-career corpus documented as 2015-2025.`,
      scope: `${paired.length} ATP players with both published ${key} rates; each operand independently clears ${key}_n>=30. This analysis includes ATP entries only.`,
      caveat: `Recent matches are a subset of the source-career corpus, not an independent period. Exact match counts, opponent strength, age, tournament mix, and player-specific latest match dates are not published; source as-of is the claim-computation timestamp. Unknown and carpet surfaces are excluded, while retirements remain decided matches under the source winner field. ${key === "grass" ? `Only ${paired.length} players qualify, so grass comparisons are especially sparse. ` : ""}These historical differences do not establish persistence or forecast performance.`,
      status: key === "grass" ? "Descriptive sparse subset" : "Descriptive subset",
      fields: [f("recent_minus_career", "Recent minus career", "pp", 2), f("recent_rate", "Recent win rate", "percent", 2), f("career_rate", "Career win rate", "percent", 2)],
      rows: paired,
      formula: "displayed difference (pp) = 100 * (surface win rate for matches on or after 2023-01-01 - source-career surface win rate documented as 2015-2025); stored value remains the unscaled fraction",
      interpretation: "Positive values mean the recorded recent-window rate is higher; negative values mean it is lower. Read both overlapping-window operands beside the difference.",
      references: REFERENCES,
      novelty: "Derived analysis",
      asOf,
    };
  });
}

export function getTennisWindowResearch(): ResearchAnalysis[] {
  return buildTennisWindowResearch(snapshot<TennisWindowAtlas>("atlas_tennis_manifest"));
}
