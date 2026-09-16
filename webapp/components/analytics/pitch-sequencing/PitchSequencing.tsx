"use client";

import { useEffect, useState } from "react";
import { Figure } from "@/components/analytics/charts/Figure";
import { pitchSequencingViewSearch, readPitchSequencingViewState, type PitchSequencingViewState } from "@/lib/analytics/inspectorViewState";
import { pitchCell, type PitchSequencingData } from "@/lib/analytics/pitchSequencing";
import { sequentialInk } from "@/lib/analytics/chartInk";

function percent(value: number | null): string {
  return value === null ? "Not published" : `${(value * 100).toFixed(1)}%`;
}

function count(value: number | null): string {
  return value === null ? "Not published" : value.toLocaleString("en-US");
}

function scaleStep(value: number, maximum: number): number {
  return Math.min(4, Math.max(0, Math.round((maximum ? value / maximum : 0) * 4)));
}

export function PitchSequencing({ data }: { data: PitchSequencingData }) {
  const defaults = { classId: data.classes[0]?.id || "", from: data.pitchTypes[0] || "", to: data.pitchTypes[0] || "" };
  const [view, setView] = useState<PitchSequencingViewState>(defaults);
  const [restored, setRestored] = useState(false);
  const selectedClass = data.classes.find(item => item.id === view.classId) || data.classes[0];
  const row = data.pitchTypes.indexOf(view.from);
  const column = data.pitchTypes.indexOf(view.to);
  const activeCell = selectedClass && row >= 0 && column >= 0 ? pitchCell(data, selectedClass, row, column) : null;
  const probabilityMaximum = Math.max(0, ...selectedClass?.probabilityMatrix.flat().filter((value): value is number => value !== null) || []);

  useEffect(() => {
    const restore = () => { setView(readPitchSequencingViewState(window.location.search, data)); setRestored(true); };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [data]);

  useEffect(() => {
    if (!restored) return;
    const url = new URL(window.location.href);
    const search = pitchSequencingViewSearch(url.search, view, data);
    window.history.replaceState(window.history.state, "", `${url.pathname}${search ? `?${search}` : ""}${url.hash}`);
  }, [data, restored, view]);

  if (!selectedClass || !data.pitchTypes.length) return <p className="ps-empty">No published pitch-sequencing rows are available in this snapshot.</p>;

  return <section className="ps-shell" aria-label="Pitch sequencing matrix">
    <div className="ps-controls" aria-label="Count class selector">
      {data.classes.map(item => <button key={item.id} type="button" aria-pressed={item.id === selectedClass.id} onClick={() => setView({ classId: item.id, from: defaults.from, to: defaults.to })}>{item.id}</button>)}
    </div>
    <p className="ps-definition"><span className="mono">{selectedClass.id}</span>: {selectedClass.definition}</p>
    <p className="ps-coverage">Published axis coverage: {percent(selectedClass.coverage)}</p>
    <p className="ps-partition">Behind, even, and ahead are disjoint classes. Two-strike and three-ball are overlapping views, not additive classes.</p>
    <Figure source="public/data/showcase/pitch_sequencing.json" asOf={data.asOf || "Published snapshot"} title="Previous pitch to next pitch" subtitle="Rows are the previous pitch type; columns are the next pitch type. Select a cell for its published details." note="Each probability uses the complete published row denominator. Rows can total below 100% because next-pitch types outside the displayed axis remain off-axis.">
      <p className="ps-scale-legend">Sequential scale: 0.0% to {percent(probabilityMaximum)}; hatched cells: below published floor.</p>
      <div className="ps-matrix-wrap">
        <svg className="ps-matrix" viewBox={`0 0 ${116 + data.pitchTypes.length * 76} ${98 + data.pitchTypes.length * 58}`} role="group" aria-label={`${selectedClass.id} pitch sequencing heatmap`} data-testid="pitch-sequencing-heatmap">
          <defs><pattern id="ps-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" fill="var(--chart-missing)" /><line x1="0" x2="0" y2="7" stroke="var(--rule-strong)" strokeWidth="2" /></pattern></defs>
          <text className="ps-axis-label" x="10" y="17">Previous pitch</text>
          <text className="ps-axis-label" x="116" y="17">Next pitch</text>
          {data.pitchTypes.map((type, column) => <text key={`column-${type}`} className="ps-axis" x={126 + column * 76} y="44" textAnchor="middle">{type}</text>)}
          {data.pitchTypes.map((from, row) => <g key={from}>
            <text className="ps-axis" x="102" y={82 + row * 58} textAnchor="end">{from}</text>
            {data.pitchTypes.map((to, column) => {
              const cell = pitchCell(data, selectedClass, row, column);
              if (!cell) return null;
              const step = cell.probability === null ? 0 : scaleStep(cell.probability, probabilityMaximum);
              const selectedCell = view.from === from && view.to === to;
              const activate = () => setView({ classId: selectedClass.id, from, to });
              return <g key={to} role="button" tabIndex={0} aria-label={`${from} to ${to}: ${cell.masked ? "masked row" : percent(cell.probability)}`} onClick={activate} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(); } }}>
                <rect className={`ps-cell ${cell.masked ? "ps-cell-missing" : `ps-cell-seq-${step}`} ${selectedCell ? "ps-selected" : ""}`} x={108 + column * 76} y={58 + row * 58} width="70" height="52" rx="4" fill={cell.masked ? "url(#ps-hatch)" : undefined} />
                {!cell.masked && <text className="ps-value" data-ink={sequentialInk(step)} x={143 + column * 76} y={88 + row * 58} textAnchor="middle">{percent(cell.probability)}</text>}
              </g>;
            })}
          </g>)}
        </svg>
      </div>
    </Figure>
    <div className="ps-table-wrap" role="region" aria-label={`${selectedClass.id} pitch sequencing table`} data-scroll-region>
      <table className="ps-table">
        <caption>{selectedClass.id} conditional pitch sequencing probabilities</caption>
        <thead><tr><th scope="col">Previous pitch</th><th scope="col">Published row denominator</th>{data.pitchTypes.map(type => <th scope="col" key={type}>{type}</th>)}</tr></thead>
        <tbody>{data.pitchTypes.map((from, rowIndex) => <tr key={from}><th scope="row">{from}</th><td>{count(selectedClass.rowNFrom[rowIndex] ?? null)}</td>{data.pitchTypes.map((to, columnIndex) => {
          const cell = pitchCell(data, selectedClass, rowIndex, columnIndex);
          if (!cell) return <td key={to}>Not published</td>;
          const detail = cell.masked ? "masked row; denominator below published floor" : `${percent(cell.probability)}; count ${count(cell.count)}`;
          const selectedCell = view.from === from && view.to === to;
          const step = cell.probability === null ? 0 : scaleStep(cell.probability, probabilityMaximum);
          return <td key={to} className={cell.masked ? "ps-table-missing" : `ps-table-seq-${step}`} title={`${from} to ${to}: ${detail}`} aria-label={`${from} to ${to}: ${detail}`}><button type="button" data-ink={cell.masked ? undefined : sequentialInk(step)} aria-pressed={selectedCell} aria-label={`Select ${from} to ${to}`} onClick={() => setView({ classId: selectedClass.id, from, to })}>{cell.masked ? "Masked below floor" : percent(cell.probability)}</button></td>;
        })}</tr>)}</tbody>
      </table>
    </div>
    <div className="ps-detail" aria-live="polite">
      <p className="ps-detail-label">Selected transition</p>
      {activeCell && <><h3>{activeCell.from} to {activeCell.to}</h3>{activeCell.masked ? <p>This previous-pitch row is masked because its published denominator is below the floor of {count(data.rowMinN)} transitions.</p> : <dl><div><dt>Count</dt><dd>{count(activeCell.count)}</dd></div><div><dt>Row denominator</dt><dd>{count(activeCell.denominator)}</dd></div><div><dt>Conditional probability</dt><dd>{percent(activeCell.probability)}</dd></div></dl>}</>}
    </div>
    <p className="ps-source-fields">Source fields: pitch_sequencing.json -&gt; pitch_types[], by_class[].prob_matrix[row][column], count_matrix[row][column], row_n_from[row], row_below_floor[row], coverage, and floors.row_min_n.</p>
  </section>;
}

export default PitchSequencing;
