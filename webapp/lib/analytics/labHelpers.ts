import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { LabField, LabRow } from "./labTypes";
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
