import { field as f, snapshot } from "./labHelpers";
import type { LabDataset, LabRow } from "./labTypes";

type SourceObject = Record<string, unknown>;
const object = (value: unknown): value is SourceObject => value !== null && typeof value === "object" && !Array.isArray(value);
const finite = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const count = (value: unknown): number | null =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
const named = (value: unknown): string | undefined => typeof value === "string" && value.trim() ? value : undefined;
const sportName = (sport: string) => sport.replace("soccer_intl", "International soccer").toUpperCase();
const available = (value: number | null) => value === null ? "unavailable" : String(value);

function artifactDate(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value ? value : null;
}

export function buildLiveClockLabDataset(source: unknown): LabDataset {
  if (!object(source) || !Array.isArray(source.results)) {
    throw new Error("novel_live_clock_fraction.results must be an array");
  }
  const fields = [
    f("live_clock_fraction", "Live-clock fraction", "percent"),
    f("decided_frac_of_games", "Games decided by threshold", "percent"),
    f("n_games_total", "Games with usable score paths", "number", 0),
    f("n_games_decided", "Games decided", "number", 0),
  ];
  const scopeParts: string[] = [];
  const rows: LabRow[] = source.results.map((raw, index) => {
    const path = `novel_live_clock_fraction.results[${index}]`;
    if (!object(raw)) throw new Error(`${path} must be an object`);
    const sport = named(raw.sport);
    if (!sport) throw new Error(`${path}.sport must be a nonempty string`);
    const label = sportName(sport);
    const total = count(raw.n_games_total);
    const decided = count(raw.n_games_decided);
    const threshold = finite(raw.near_median_threshold);
    const unit = named(raw.unit);
    const clockField = named(raw.clock_field);
    scopeParts.push(`${label}: ${available(total)} games with usable score paths`);
    return {
      id: `${label}-${index}`,
      label,
      group: label,
      values: {
        live_clock_fraction: finite(raw.live_clock_fraction),
        decided_frac_of_games: finite(raw.decided_frac_of_games),
        n_games_total: total,
        n_games_decided: decided,
      },
      note: `Source: novel_live_clock_fraction.json results[${index}]. ` +
        `Threshold: ${available(threshold)} ${unit ?? "(score unit unavailable)"}. ` +
        `Clock: ${clockField ?? "unavailable"}. ` +
        `At this threshold, ${available(decided)} of ${available(total)} games with usable score paths were decided. ` +
        "The source does not publish the stored corpus game count for this row.",
      definition: {
        sport: label,
        ...(threshold === null ? {} : { threshold }),
        ...(unit ? { unit } : {}),
        ...(clockField ? { clockField } : {}),
        ...(total === null ? {} : { population: `${total} games with usable score paths` }),
      },
    };
  });
  const date = artifactDate(source.as_of);
  return {
    id: "live-clock",
    title: "Live-Clock Fraction",
    sport: "all",
    category: "Experimental metrics",
    source: "novel_live_clock_fraction",
    description: "The median share of the observed game clock at which a score gap becomes permanent among threshold-decided games; the decided-game share uses all games with usable score paths.",
    scope: `${scopeParts.length ? scopeParts.join("; ") : "No sport rows published"}. ` +
      `Artifact date: ${date ?? "unavailable"}; observation window unavailable. ` +
      "These are games with usable score paths. The LCF artifact does not include stored corpus counts; see the integrity receipt for those counts.",
    caveat: "Sport-specific score thresholds and clock units are not equivalent, so the rows do not support a universal cross-sport excitement score. This descriptive score-path metric does not establish why a lead held or predict a live game's result. NBA and tennis are not buildable in this artifact because no blowout corpus is available.",
    status: "Incremental metric",
    fields,
    rows,
  };
}

export function getLiveClockLabDataset(): LabDataset {
  return buildLiveClockLabDataset(snapshot<unknown>("novel_live_clock_fraction"));
}
