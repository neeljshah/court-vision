"use client";

import { useState } from "react";
import { Figure } from "@/components/analytics/charts/Figure";
import { luminance, seqColor } from "@/components/analytics/charts/scale";
import { pitchCell, type PitchSequencingData } from "@/lib/analytics/pitchSequencing";

function percent(value: number | null): string {
  return value === null ? "Not published" : `${(value * 100).toFixed(1)}%`;
}

function count(value: number | null): string {
  return value === null ? "Not published" : value.toLocaleString("en-US");
}

export function PitchSequencing({ data }: { data: PitchSequencingData }) {
  const [classId, setClassId] = useState(data.classes[0]?.id || "");
  const [selected, setSelected] = useState({ row: 0, column: 0 });
  const selectedClass = data.classes.find(item => item.id === classId) || data.classes[0];
  const activeCell = selectedClass ? pitchCell(data, selectedClass, selected.row, selected.column) : null;

  if (!selectedClass || !data.pitchTypes.length) return <p className="ps-empty">No published pitch-sequencing rows are available in this snapshot.</p>;

  return <section className="ps-shell" aria-label="Pitch sequencing matrix">
    <div className="ps-controls" aria-label="Count class selector">
      {data.classes.map(item => <button key={item.id} type="button" aria-pressed={item.id === selectedClass.id} onClick={() => { setClassId(item.id); setSelected({ row: 0, column: 0 }); }}>{item.id}</button>)}
    </div>
    <p className="ps-definition"><span className="mono">{selectedClass.id}</span>: {selectedClass.definition}</p>
    <p className="ps-coverage">Published axis coverage: {percent(selectedClass.coverage)}</p>
    <p className="ps-partition">Behind, even, and ahead are disjoint classes. Two-strike and three-ball are overlapping views, not additive classes.</p>
    <Figure source="public/data/showcase/pitch_sequencing.json" asOf={data.asOf || "Published snapshot"} title="Previous pitch to next pitch" subtitle="Rows are the previous pitch type; columns are the next pitch type. Select a cell for its published details." note="Each probability uses the complete published row denominator. Rows can total below 100% because next-pitch types outside the displayed axis remain off-axis.">
      <div className="ps-matrix-wrap">
        <svg className="ps-matrix" viewBox={`0 0 ${116 + data.pitchTypes.length * 76} ${98 + data.pitchTypes.length * 58}`} role="img" aria-label={`${selectedClass.id} pitch sequencing heatmap`} data-testid="pitch-sequencing-heatmap">
          <defs><pattern id="ps-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" fill="var(--paper-tint)" /><line x1="0" x2="0" y2="7" stroke="var(--rule-strong)" strokeWidth="2" /></pattern></defs>
          <text className="ps-axis-label" x="10" y="17">Previous pitch</text>
          <text className="ps-axis-label" x="116" y="17">Next pitch</text>
          {data.pitchTypes.map((type, column) => <text key={`column-${type}`} className="ps-axis" x={126 + column * 76} y="44" textAnchor="middle">{type}</text>)}
          {data.pitchTypes.map((from, row) => <g key={from}>
            <text className="ps-axis" x="102" y={82 + row * 58} textAnchor="end">{from}</text>
            {data.pitchTypes.map((to, column) => {
              const cell = pitchCell(data, selectedClass, row, column);
              if (!cell) return null;
              const color = cell.probability === null ? "var(--paper-tint)" : seqColor(cell.probability / 0.6);
              const selectedCell = selected.row === row && selected.column === column;
              const activate = () => setSelected({ row, column });
              return <g key={to} role="button" tabIndex={0} aria-label={`${from} to ${to}: ${cell.masked ? "masked row" : percent(cell.probability)}`} onClick={activate} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); activate(); } }}>
                <rect className={selectedCell ? "ps-cell ps-selected" : "ps-cell"} x={108 + column * 76} y={58 + row * 58} width="70" height="52" rx="4" fill={cell.masked ? "url(#ps-hatch)" : color} />
                {!cell.masked && <text x={143 + column * 76} y={88 + row * 58} textAnchor="middle" fill={luminance(color) < 0.56 ? "#FFFFFF" : "#182630"}>{percent(cell.probability)}</text>}
              </g>;
            })}
          </g>)}
        </svg>
      </div>
    </Figure>
    <div className="ps-detail" aria-live="polite">
      <p className="ps-detail-label">Selected transition</p>
      {activeCell && <><h3>{activeCell.from} to {activeCell.to}</h3>{activeCell.masked ? <p>This previous-pitch row is masked because its published denominator is below the floor of {count(data.rowMinN)} transitions.</p> : <dl><div><dt>Count</dt><dd>{count(activeCell.count)}</dd></div><div><dt>Row denominator</dt><dd>{count(activeCell.denominator)}</dd></div><div><dt>Conditional probability</dt><dd>{percent(activeCell.probability)}</dd></div></dl>}</>}
    </div>
    <p className="ps-source-fields">Source fields: pitch_sequencing.json -&gt; pitch_types[], by_class[].prob_matrix[row][column], count_matrix[row][column], row_n_from[row], row_below_floor[row], coverage, and floors.row_min_n.</p>
  </section>;
}

export default PitchSequencing;
