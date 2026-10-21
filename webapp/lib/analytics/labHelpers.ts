import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { LabAsOf, LabField, LabRow } from "./labTypes";
export type SourceRow = Record<string, unknown>;
export function snapshot<T>(id: string): T {
  const raw = readFileSync(join(process.cwd(), "public/data/showcase", `${id}.json`), "utf8");
  return JSON.parse(raw.replace(/"(?:\\.|[^"\\])*"|\bNaN\b/g, token => token === "NaN" ? "null" : token));
}
export const field = (key: string, label: string, unit: LabField["unit"] = "number", digits = 2): LabField => ({ key, label, unit, digits });
export function labRows(rows: SourceRow[], fields: LabField[], name: string, group: string | ((row: SourceRow, index: number) => string) = "Published rows"): LabRow[] {
  return rows.map((r, index) => { const rowGroup = typeof group === "function" ? group(r, index) : group; return { id: `${rowGroup}-${index}`, label: String(r[name] ?? `Row ${index + 1}`), group: rowGroup,
    values: Object.fromEntries(fields.map(f => [f.key, typeof r[f.key] === "number" && Number.isFinite(r[f.key]) ? r[f.key] as number : null])),
    note: typeof r.note === "string" ? r.note : undefined,
  }; });
}
/** Source fields that may carry a generation stamp, in the order they are consulted. */
export const AS_OF_FIELDS = ["as_of", "generated_at", "built_at", "created_at", "updated_at"] as const;
function calendarDate(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?$/.exec(value.trim());
  if (!match) return null;
  const [year, month, day] = match.slice(1, 4).map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day ? match[0].trim().slice(0, 10) : null;
}
/** The first published generation stamp on a source JSON, as a calendar date plus the field it came from; undefined when none is published. */
export function sourceAsOf(source: unknown): LabAsOf | undefined {
  if (source === null || typeof source !== "object" || Array.isArray(source)) return undefined;
  for (const field of AS_OF_FIELDS) {
    const date = calendarDate((source as Record<string, unknown>)[field]);
    if (date) return { date, field };
  }
  return undefined;
}
