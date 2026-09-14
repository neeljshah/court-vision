"use client";
import { displayMeasurement as display, type LabField, type LabRow } from "@/lib/analytics/labTypes";

export function RankedPlot({ rows, field, onSelect }: { rows: LabRow[]; field: LabField; onSelect: (r: LabRow) => void }) {
  const values = rows.map(r => r.values[field.key]!).filter(Number.isFinite);
  const min = Math.min(0, ...values); const max = Math.max(0, ...values);
  const span = max - min || 1; const zero = -min / span * 100;
  return <div className="lab-ranks"><div className="lab-axis"><span>{display(min, field)}</span><span>{field.label}</span><span>{display(max, field)}</span></div>
    {rows.slice(0, 16).map((r, i) => { const value = r.values[field.key]!; const x = (value - min) / span * 100;
      return <button key={r.id} className="lab-rank" onClick={() => onSelect(r)} aria-label={`Inspect ${r.label}: ${display(value, field)}`}>
        <span className="lab-rank-number">{i + 1}</span><span className="lab-rank-label" title={r.label}>{r.label}<small>{r.group}</small></span>
        <span className="lab-rank-track"><i className="lab-zero" style={{ left: `${zero}%` }} /><i className={value < 0 ? "lab-bar-negative" : "lab-bar-positive"} style={{ left: `${Math.min(x, zero)}%`, width: `${Math.abs(x - zero)}%` }} /></span><b>{display(value, field)}</b>
      </button>;
    })}
    <p className="cv-footnote">Showing {Math.min(16, rows.length)} of {rows.length} matching numeric rows. Open a row to inspect all its fields. Rankings apply only to the published subset.</p>
  </div>;
}
export function ScatterPlot({ rows, x, y, onSelect }: { rows: LabRow[]; x: LabField; y: LabField; onSelect: (r: LabRow) => void }) {
  const paired = rows.filter(r => r.values[x.key] !== null && r.values[y.key] !== null && Number.isFinite(r.values[x.key]) && Number.isFinite(r.values[y.key]));
  if (!paired.length) return <div className="cv-empty">No rows contain both selected measurements.</div>;
  const xs = paired.map(r => r.values[x.key]!); const ys = paired.map(r => r.values[y.key]!);
  const loX = Math.min(...xs), hiX = Math.max(...xs), loY = Math.min(...ys), hiY = Math.max(...ys);
  const px = (v: number) => 75 + (v - loX) / (hiX - loX || 1) * 590;
  const py = (v: number) => 265 - (v - loY) / (hiY - loY || 1) * 225;
  return <div className="lab-scatter"><span className="lab-y-label">{y.label}</span><svg viewBox="0 0 740 325" role="group" aria-label={`${y.label} against ${x.label}; inspect individual points or use the data table`}>
    {[0, .25, .5, .75, 1].map(t => <g key={t}><line x1="75" x2="665" y1={40 + t * 225} y2={40 + t * 225} stroke="var(--cv-line)" strokeDasharray="3 4" /><text x="66" y={44 + t * 225} textAnchor="end">{display(hiY - t * (hiY - loY), y)}</text><text x={75 + t * 590} y="290" textAnchor="middle">{display(loX + t * (hiX - loX), x)}</text></g>)}
    {paired.map(r => <circle key={r.id} cx={px(r.values[x.key]!)} cy={py(r.values[y.key]!)} r="5" role="button" tabIndex={0} focusable="true" aria-label={`Inspect ${r.label}: ${x.label} ${display(r.values[x.key], x)}; ${y.label} ${display(r.values[y.key], y)}`} onClick={() => onSelect(r)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(r); } }}><title>{`${r.label}: ${x.label} ${display(r.values[x.key], x)}; ${y.label} ${display(r.values[y.key], y)}`}</title></circle>)}
    <text x="370" y="321" textAnchor="middle">{x.label}</text>
  </svg><p className="cv-footnote">{paired.length} paired rows. Axes span the selected data. This plot does not estimate a causal relationship or a fitted prediction.</p></div>;
}
