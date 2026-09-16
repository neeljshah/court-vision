import Link from "next/link";
import { atlasFieldDefinition } from "@/lib/analytics/atlasFieldDefinitions";
import { getEntityMeasurementSchema } from "@/lib/analytics/entityMeasurementSchemas";
import { asOfDate } from "@/lib/analytics/format";

export type CalibrationEntry = {
  entity: string;
  card_path: string;
  card_type?: string;
  sport?: string;
  key_numbers: Record<string, unknown>;
  as_of?: string;
};

type Props = {
  entries: CalibrationEntry[];
  heading: string;
  id: string;
};

function slugFor(entry: CalibrationEntry): string {
  return (entry.card_path.split(/[\\/]/).pop() || entry.entity).replace(/\.[a-z0-9]+$/i, "");
}

function displayName(entry: CalibrationEntry): string {
  return entry.entity.replace(/_/g, " ");
}

function isScalar(value: unknown): value is string | number | boolean {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

function formatValue(key: string, value: string | number | boolean): string {
  const field = atlasFieldDefinition("calibration", key);
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "string") return value;
  if (field.unit === "percent-already") return `${value.toFixed(field.decimals)}%`;
  if (field.unit === "fraction-as-percent") return `${(value * 100).toFixed(field.decimals)}%`;
  if (field.unit === "mph") return `${value.toFixed(field.decimals)} mph`;
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(field.decimals)));
}

export function CalibrationTableSection({ entries, heading, id }: Props) {
  const schema = getEntityMeasurementSchema("calibration", entries[0] || {});
  const scalarFields = schema.fields.filter((key) => key !== "by_time_bucket");
  const fields = scalarFields.filter((key) => entries.some((entry) => isScalar(entry.key_numbers[key])));
  const unpublished = scalarFields.filter((key) => !fields.includes(key));
  const asOf = asOfDate(entries[0]?.as_of);

  return <section id={id} className="pl-anchor pl-fsec" style={{ marginTop: 44 }}>
    <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 6, flexWrap: "wrap" }}>
      <span aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: "#8A8078" }} />
      <h3 className="serif" style={{ fontWeight: 500, fontSize: 24 }}>{heading}</h3>
      <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{entries.length.toLocaleString()} cards{asOf ? ` \u00B7 as of ${asOf}` : ""}</span>
    </div>
    <p style={{ color: "var(--ink-3)", fontSize: 12, marginBottom: 14 }}>
      Published fields: {fields.map((key) => atlasFieldDefinition("calibration", key).label).join("; ")}.
    </p>
    <div className="pl-tblwrap"><table className="pl-tbl"><thead><tr><th scope="col">Entity</th>{fields.map((key) => <th key={key} scope="col">{atlasFieldDefinition("calibration", key).label}</th>)}</tr></thead>
      <tbody>{entries.map((entry) => <tr key={entry.entity} data-name={displayName(entry).toLowerCase()}><td><Link href={`/analytics/players/calibration/${slugFor(entry)}`}>{displayName(entry)}</Link></td>{fields.map((key) => {
        const value = entry.key_numbers[key];
        return <td key={key} className="num">{isScalar(value) ? formatValue(key, value) : "--"}</td>;
      })}</tr>)}</tbody>
    </table></div>
    {unpublished.length ? <p style={{ color: "var(--ink-3)", fontSize: 12, marginTop: 10 }}>Unpublished for this cohort: {unpublished.map((key) => atlasFieldDefinition("calibration", key).label).join("; ")}.</p> : null}
  </section>;
}
