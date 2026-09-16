"use client";
import { useEffect, useRef, useState } from "react";
import { displayMeasurement as display, type LabField, type LabRow } from "@/lib/analytics/labTypes";

export function RankedPlot({ rows, field, onSelect }: { rows: LabRow[]; field: LabField; onSelect: (r: LabRow) => void }) {
  const numericRows = rows.filter(r => r.values[field.key] !== null && Number.isFinite(r.values[field.key]));
  const values = numericRows.map(r => r.values[field.key]!);
  const min = Math.min(0, ...values); const max = Math.max(0, ...values);
  const span = max - min || 1; const zero = -min / span * 100;
  return <div className="lab-ranks"><div className="lab-axis"><span>{display(min, field)}</span><span>{field.label}</span><span>{display(max, field)}</span></div>
    {numericRows.slice(0, 16).map((r, i) => { const value = r.values[field.key]!; const x = (value - min) / span * 100;
      return <button key={r.id} className="lab-rank" onClick={() => onSelect(r)} aria-label={`Inspect ${r.label}: ${display(value, field)}`}>
        <span className="lab-rank-number">{i + 1}</span><span className="lab-rank-label" title={r.label}>{r.label}<small>{r.group}</small></span>
        <span className="lab-rank-track"><i className="lab-zero" style={{ left: `${zero}%` }} /><i className={value < 0 ? "lab-bar-negative" : "lab-bar-positive"} style={{ left: `${Math.min(x, zero)}%`, width: `${Math.abs(x - zero)}%` }} /></span><b>{display(value, field)}</b>
      </button>;
    })}
    <p className="cv-footnote">Showing {Math.min(16, numericRows.length)} of {numericRows.length} matching numeric {numericRows.length === 1 ? "row" : "rows"}. Open a row to inspect all its fields. Rankings apply only to the published subset.</p>
  </div>;
}

function plotDomain(values: number[], field: LabField): [number, number] {
  const low = Math.min(...values), high = Math.max(...values);
  if (low !== high) return [low, high];
  const scale = field.unit === "percent" || field.unit === "pp" ? 100 : 1;
  const displayStep = 10 ** -(field.digits ?? 2) / scale;
  const padding = Math.max(Math.abs(low) * .05, displayStep * 2);
  return [low - padding, high + padding];
}

export function ScatterPlot({ rows, x, y, onSelect }: { rows: LabRow[]; x: LabField; y: LabField; onSelect: (r: LabRow) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const points = useRef(new Map<string, SVGCircleElement>());
  const [plotWidth, setPlotWidth] = useState(740);
  const [activePoint, setActivePoint] = useState("");
  useEffect(() => {
    const node = container.current;
    if (!node) return;
    const update = (width: number) => { if (width > 0) setPlotWidth(Math.round(width)); };
    update(node.getBoundingClientRect().width);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(entries => update(entries[0]?.contentRect.width || 0));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const paired = rows.filter(r => r.values[x.key] !== null && r.values[y.key] !== null && Number.isFinite(r.values[x.key]) && Number.isFinite(r.values[y.key]));
  if (!paired.length) return <div ref={container} className="lab-scatter"><div className="cv-empty">No rows contain both selected measurements.</div></div>;
  const activeId = paired.some(r => r.id === activePoint) ? activePoint : paired[0].id;
  const xs = paired.map(r => r.values[x.key]!); const ys = paired.map(r => r.values[y.key]!);
  const [loX, hiX] = plotDomain(xs, x), [loY, hiY] = plotDomain(ys, y);
  const compact = plotWidth < 500, height = 280, right = compact ? 16 : 75, top = 24, bottom = 45;
  const ticks = compact ? [0, .5, 1] : [0, .25, .5, .75, 1];
  const yLabelWidth = Math.max(...ticks.map(t => display(hiY - t * (hiY - loY), y).length)) * 7 + 16;
  const left = compact ? Math.min(112, Math.max(70, yLabelWidth)) : 75;
  const innerWidth = Math.max(1, plotWidth - left - right), innerHeight = height - top - bottom;
  const px = (v: number) => left + (v - loX) / (hiX - loX || 1) * innerWidth;
  const py = (v: number) => top + (1 - (v - loY) / (hiY - loY || 1)) * innerHeight;
  const move = (index: number) => {
    const next = paired[Math.max(0, Math.min(index, paired.length - 1))];
    setActivePoint(next.id); points.current.get(next.id)?.focus();
  };
  return <div ref={container} className="lab-scatter"><span className="lab-y-label">{y.label}</span><svg viewBox={`0 0 ${plotWidth} ${height}`} role="group" aria-label={`${y.label} against ${x.label}; inspect individual points or use the data table`}><title>{`${y.label} against ${x.label}`}</title>
    {ticks.map(t => <g key={t}><line x1={left} x2={plotWidth - right} y1={top + t * innerHeight} y2={top + t * innerHeight} stroke="var(--cv-line)" strokeDasharray="3 4" /><text x={left - 9} y={top + t * innerHeight + 4} textAnchor="end">{display(hiY - t * (hiY - loY), y)}</text><text x={left + t * innerWidth} y={height - 28} textAnchor={compact && t === 0 ? "start" : compact && t === 1 ? "end" : "middle"}>{display(loX + t * (hiX - loX), x)}</text></g>)}
    {paired.map((r, index) => <circle key={r.id} ref={node => { if (node) points.current.set(r.id, node); else points.current.delete(r.id); }} cx={px(r.values[x.key]!)} cy={py(r.values[y.key]!)} r="5" role="button" tabIndex={r.id === activeId ? 0 : -1} focusable="true" aria-label={`Inspect ${r.label}: ${x.label} ${display(r.values[x.key], x)}; ${y.label} ${display(r.values[y.key], y)}`} onFocus={() => setActivePoint(r.id)} onClick={() => { setActivePoint(r.id); onSelect(r); }} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(r); } else if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(index + 1); } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(index - 1); } else if (e.key === "Home") { e.preventDefault(); move(0); } else if (e.key === "End") { e.preventDefault(); move(paired.length - 1); } }}><title>{`${r.label}: ${x.label} ${display(r.values[x.key], x)}; ${y.label} ${display(r.values[y.key], y)}`}</title></circle>)}
    <text x={plotWidth / 2} y={height - 6} textAnchor="middle">{x.label}</text>
  </svg><p className="cv-footnote">Use Arrow keys to move through paired rows in the current row order; Home and End jump to the first and last point. Enter or Space opens a point.</p><p className="cv-footnote">{paired.length} paired {paired.length === 1 ? "row" : "rows"}. Axes span the selected data; constant measurements receive symmetric axis padding. This plot does not estimate a causal relationship or a fitted prediction.</p></div>;
}
