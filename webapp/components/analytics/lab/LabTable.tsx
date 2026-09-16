"use client";
import { useState } from "react";
import Link from "next/link";
import { displayMeasurement as display, type LabDataset, type LabRow } from "@/lib/analytics/labTypes";
import { Pagination } from "@/components/analytics/workspace/Primitives";
export function buildLabCSV(dataset: LabDataset, rows: LabRow[]): string {
  const escape = (value: string) => `"${(/^[=+@\-\t\r]/.test(value) ? "'" + value : value).replace(/"/g, '""')}"`;
  const formula = "formula" in dataset && typeof dataset.formula === "string" ? dataset.formula : null;
  const headers = ["Entity", "Group", ...dataset.fields.map(f => `${f.label} (${f.unit}; raw value)`), "Row note", "Source", "Scope", "Caveat", ...(formula ? ["Formula"] : [])];
  const lines = [headers.map(escape).join(","), ...rows.map(r => [escape(r.label), escape(r.group), ...dataset.fields.map(f => typeof r.values[f.key] === "number" && Number.isFinite(r.values[f.key]) ? String(r.values[f.key]) : ""), escape(r.note || ""), escape(dataset.source), escape(dataset.scope), escape(dataset.caveat), ...(formula ? [escape(formula)] : [])].join(","))];
  return lines.join("\r\n");
}
export function exportLabCSV(dataset: LabDataset, rows: LabRow[]) {
  const url = URL.createObjectURL(new Blob([buildLabCSV(dataset, rows)], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = `courtvision-${dataset.id}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
type LinkableLabRow = LabRow & { href?: string };
export function LabTable({ dataset, rows, onSelect }: { dataset: LabDataset; rows: LinkableLabRow[]; onSelect: (r: LabRow) => void }) {
  const [page, setPage] = useState(0); const safePage = Math.min(page, Math.max(0, Math.ceil(rows.length / 12) - 1));
  return <><div className="cv-table-scroll" tabIndex={0} role="region" aria-label="Scrollable measurements"><table className="cv-benchmark-table lab-data-table"><caption className="sr-only">{dataset.title}: all published measurement fields</caption><thead><tr><th scope="col">Entity</th>{dataset.fields.map(f => <th scope="col" key={f.key}>{f.label}</th>)}</tr></thead><tbody>{rows.slice(safePage * 12, safePage * 12 + 12).map(r => <tr key={r.id}><td>{r.href ? <Link href={r.href} prefetch={false}>{r.label}</Link> : r.label}<button type="button" aria-label={`Inspect ${r.label}`} onClick={() => onSelect(r)}>Inspect</button><span>{r.group}</span></td>{dataset.fields.map(f => <td key={f.key}>{display(r.values[f.key], f)}</td>)}</tr>)}</tbody></table></div><Pagination page={safePage} total={rows.length} onChange={setPage} /></>;
}
