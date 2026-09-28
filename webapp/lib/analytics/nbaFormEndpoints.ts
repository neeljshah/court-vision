import { field as f } from "./labHelpers";
import type { LabField } from "./labTypes";
import type { ResearchRow } from "./researchTypes";

type SourceRecord = Record<string, unknown>;

export const NBA_FORM_FIELDS: LabField[] = [
  f("relative_change", "Endpoint relative change", "percent", 2),
  f("delta", "Recomputed endpoint change", "number", 3),
  f("first", "First 10-game composite", "number", 3),
  f("last", "Last 10-game composite", "number", 3),
  f("last_percentile", "Last league percentile", "percent", 2),
  f("games", "Qualifying games", "number", 0),
  f("endpoint_days", "Days between window ends", "number", 0),
  f("qual_minutes", "Qualifying minutes", "number", 1),
  f("source_delta", "Published endpoint change", "number", 3),
];

const record = (value: unknown): value is SourceRecord =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const finite = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
const nonnegative = (value: unknown): number | null => {
  const number = finite(value);
  return number !== null && number >= 0 ? number : null;
};
const count = (value: unknown): number | null => {
  const number = nonnegative(value);
  return number !== null && Number.isSafeInteger(number) ? number : null;
};
const percentile = (value: unknown): number | null => {
  const number = finite(value);
  return number !== null && number >= 0 && number <= 100 ? number / 100 : null;
};

function isoDate(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value ? value : null;
}

function endpointDays(first: string | null, last: string | null): number | null {
  if (first === null || last === null) return null;
  const days = (Date.parse(`${last}T00:00:00Z`) - Date.parse(`${first}T00:00:00Z`)) / 86_400_000;
  return days >= 0 ? days : null;
}

function sourceRows(source: SourceRecord, key: "top_movers_risers" | "top_movers_fallers") {
  return Array.isArray(source[key]) ? source[key] : [];
}

export function buildNbaFormRows(source: unknown): ResearchRow[] {
  if (!record(source)) return [];
  const risers = sourceRows(source, "top_movers_risers");
  const fallers = sourceRows(source, "top_movers_fallers");
  return [...risers, ...fallers].flatMap((entry, index): ResearchRow[] => {
    if (!record(entry) || typeof entry.player_name !== "string" || !entry.player_name.trim()) return [];
    const first = finite(entry.first_form);
    const last = finite(entry.last_form);
    const delta = first !== null && last !== null ? finite(last - first) : null;
    const firstDate = isoDate(entry.first_date);
    const lastDate = isoDate(entry.last_date);
    const sourceKey = index < risers.length ? "top_movers_risers" : "top_movers_fallers";
    const sourceIndex = sourceKey === "top_movers_risers" ? index : index - risers.length;
    const path = `${sourceKey}[${sourceIndex}]`;
    return [{
      id: `form-${index}`,
      label: entry.player_name,
      group: sourceKey === "top_movers_risers" ? "Published risers" : "Published fallers",
      values: {
        relative_change: first !== null && first !== 0 && delta !== null ? finite(delta / Math.abs(first)) : null,
        delta,
        first,
        last,
        last_percentile: percentile(entry.last_form_league_pctile),
        games: count(entry.n_qual_games),
        endpoint_days: endpointDays(firstDate, lastDate),
        qual_minutes: nonnegative(entry.qual_minutes),
        source_delta: finite(entry.delta),
      },
      note: `${firstDate ?? "Unknown"} and ${lastDate ?? "Unknown"} are ends of the first and last retained 10-game windows. Published and recomputed changes may differ by 0.001 because endpoints were rounded separately. Qualifying games and minutes cover all games meeting the 8-minute floor, not only games between those end dates.`,
      sourcePaths: [
        `${path}.first_form`, `${path}.last_form`, `${path}.delta`,
        `${path}.last_form_league_pctile`, `${path}.n_qual_games`, `${path}.qual_minutes`,
        `${path}.first_date`, `${path}.last_date`,
      ],
      bindingValues: { first_window_end: firstDate, last_window_end: lastDate },
    }];
  });
}
