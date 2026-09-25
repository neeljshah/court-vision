import Link from "next/link";
import { Figure } from "@/components/analytics/charts/Figure";
import type { TimingModuleEvidence } from "@/lib/analytics/timingModuleEvidence";

function cell(value: string | number | null | undefined): string {
  if (value == null) return "Unavailable";
  return typeof value === "number" ? value.toLocaleString("en-US", { maximumFractionDigits: 4 }) : value;
}

export function TimingModulePanel({ evidence, source, moduleId }: {
  evidence: TimingModuleEvidence; source: string; moduleId: string;
}) {
  const dataset = moduleId === "novel_live_clock_fraction" ? "live-clock" : "market-foresight";
  return <section className="timing-module" aria-label="Timing measurement evidence">
    <div className="timing-method">
      <h2 className="overline">How to read these measurements</h2>
      <p>{evidence.method}</p>
      <p className="timing-limit">{evidence.caveat}</p>
    </div>
    <Figure source={source} asOf={evidence.snapshotDate} dateKind="published"
      title="Published measurements" denominator={evidence.denominator} verdict="descriptive_only">
      {evidence.tables.map(table => <details className="timing-population" key={table.id} open>
        <summary><span>{table.title}</span><span className="timing-row-count">{table.rows.length} published {table.rows.length === 1 ? "row" : "rows"}</span></summary>
        <div className="timing-scroll" role="region" tabIndex={0} aria-label={`${table.title} measurements (scrollable table)`} data-scroll-region>
          <table>
            <caption className="sr-only">{table.title} published timing measurements</caption>
            <thead><tr>{table.columns.map(column => <th key={column.key} scope="col">{column.label}</th>)}</tr></thead>
            <tbody>{table.rows.map((row, index) => <tr key={index}>{table.columns.map((column, columnIndex) => columnIndex === 0
              ? <th scope="row" key={column.key}>{cell(row[column.key])}</th>
              : <td key={column.key}>{cell(row[column.key])}</td>)}</tr>)}</tbody>
          </table>
        </div>
        {!table.rows.length && <p className="timing-missing">No measurement rows are published for this population.</p>}
      </details>)}
      {!evidence.tables.length && <p className="timing-missing">No timing measurement rows are published in this artifact.</p>}
    </Figure>
    {evidence.missing.length > 0 && <div className="timing-missing"><h3 className="overline">Coverage and missing fields</h3><ul>{evidence.missing.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
    <Link className="timing-lab" href={`/analytics/lab/?dataset=${dataset}&view=table&allCohorts=1`}>Explore these measurements in the lab</Link>
    <style>{`.timing-module{min-width:0}.timing-method{margin:0 0 24px}.timing-method p{font-size:14px;line-height:1.65;color:var(--ink-2);margin:9px 0}.timing-limit{padding-left:14px;border-left:3px solid var(--signal)}.timing-population{border:1px solid var(--rule);border-radius:var(--radius-card);background:var(--paper-raised);margin:0 0 16px;overflow:hidden}.timing-population summary{cursor:pointer;padding:16px;font-weight:600;line-height:1.5}.timing-population summary:focus-visible,.timing-scroll:focus-visible{outline:2px solid var(--accent);outline-offset:-3px}.timing-row-count{display:block;margin-left:18px;font-family:var(--font-mono);font-size:11px;font-weight:400;color:var(--ink-3)}.timing-scroll{max-width:100%;overflow-x:auto}.timing-scroll table{width:100%;min-width:640px;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}.timing-scroll th,.timing-scroll td{padding:11px 14px;border-top:1px solid var(--rule);text-align:right;vertical-align:top;line-height:1.45}.timing-scroll th{font-weight:500}.timing-scroll thead th{font-size:11px;color:var(--ink-3);text-align:right;background:var(--paper-tint)}.timing-scroll th:first-child{text-align:left}.timing-scroll tbody tr:hover{background:var(--paper-tint)}.timing-missing{margin:18px 0;font-size:13px;line-height:1.6;color:var(--ink-2)}.timing-missing ul{padding-left:20px}.timing-lab{display:inline-block;margin:18px 0;color:var(--accent);font-size:14px;text-decoration:underline;text-underline-offset:4px}`}</style>
  </section>;
}

export function TimingModuleReceipts({ evidence }: { evidence: TimingModuleEvidence }) {
  return <dl className="timing-receipts" aria-label="Timing measurement receipts">
    {evidence.receipts.map((receipt, index) => <div key={index}><dt>{receipt.label}</dt><dd>{receipt.value}</dd></div>)}
    <style>{`.timing-receipts{margin:0}.timing-receipts div{padding:10px 0;border-bottom:1px solid var(--rule)}.timing-receipts dt{font-size:11px;line-height:1.5;color:var(--ink-3)}.timing-receipts dd{margin:3px 0 0;font-size:14px;line-height:1.5;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}`}</style>
  </dl>;
}
