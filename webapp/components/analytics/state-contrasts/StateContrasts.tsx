"use client";

import { useState } from "react";
import { Figure } from "@/components/analytics/charts/Figure";
import { contrastsForPair, deltaPercentagePoints, sameBandContrasts, type StateContrast, type StateContrastSport } from "@/lib/analytics/stateContrasts";

const SOURCE = "public/data/showcase/why_attribution.json";

function sportLabel(sport: string): string {
  return sport === "mlb" ? "MLB" : sport === "soccer_intl" ? "International soccer" : sport.replace(/_/g, " ");
}

function percent(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function percentagePoints(value: number): string {
  const points = deltaPercentagePoints(value);
  return `${points > 0 ? "+" : ""}${points.toFixed(2)} pp`;
}

function pairLabel(fromTime: string, toTime: string): string {
  return `${fromTime} to ${toTime}`;
}

function stateLabel(contrast: StateContrast, side: "from" | "to"): string {
  const population = contrast[side];
  return `${population.time} / ${population.probabilityBand}`;
}

function maxDelta(rows: StateContrast[]): number {
  return Math.max(1, ...rows.map(row => Math.abs(deltaPercentagePoints(row.winprobDelta))));
}

export function StateContrasts({ sports }: { sports: StateContrastSport[] }) {
  const [sport, setSport] = useState(sports[0]?.sport || "");
  const selectedSport = sports.find(item => item.sport === sport) || sports[0];
  const pairs = selectedSport?.adjacentTimePairs || [];
  const [pairId, setPairId] = useState(pairs[0]?.id || "");
  const selectedPair = pairs.find(pair => pair.id === pairId) || pairs[0];
  const [bandScope, setBandScope] = useState("same");
  const [sort, setSort] = useState<"difference" | "support">("difference");
  const [showFullTable, setShowFullTable] = useState(false);
  const pairRows = selectedSport && selectedPair ? contrastsForPair(sports, selectedSport.sport, selectedPair.id) : [];
  const originBands = Array.from(new Set(pairRows.map(row => row.from.probabilityBand)));
  const scopedRows = bandScope === "same"
    ? sameBandContrasts(pairRows)
    : bandScope === "all"
      ? pairRows
      : pairRows.filter(row => row.from.probabilityBand === bandScope);
  const isFilteredEmpty = pairRows.length > 0 && scopedRows.length === 0;
  const visibleRows = isFilteredEmpty ? pairRows : scopedRows;
  const filterEmptyMessage = bandScope === "same"
    ? "No same-band contrasts in this pair; showing all bands."
    : `No contrasts for band ${bandScope} in this pair; showing all bands.`;
  const rows = [...visibleRows].sort((a, b) => sort === "difference"
    ? Math.abs(b.winprobDelta) - Math.abs(a.winprobDelta) || b.minSupportN - a.minSupportN
    : b.minSupportN - a.minSupportN || Math.abs(b.winprobDelta) - Math.abs(a.winprobDelta));
  const scale = maxDelta(rows);

  if (!sports.length) return <p className="sc-empty">No published state contrasts are available in this snapshot.</p>;

  function chooseSport(nextSport: string) {
    const next = sports.find(item => item.sport === nextSport);
    setSport(nextSport);
    setPairId(next?.adjacentTimePairs[0]?.id || "");
    setBandScope("same");
    setShowFullTable(false);
  }

  function choosePair(nextPairId: string) {
    const nextRows = selectedSport ? contrastsForPair(sports, selectedSport.sport, nextPairId) : [];
    const nextBands = new Set(nextRows.map(row => row.from.probabilityBand));
    setPairId(nextPairId);
    setBandScope(current => current === "same" || current === "all" || nextBands.has(current) ? current : "same");
    setShowFullTable(false);
  }

  return <section className="sc-shell" aria-label="State contrast explorer">
    <p className="sc-definition">These are BETWEEN-BUCKET differences in outcome frequency, not transition frequencies and not paired movements within individual games. Holding the forecast band fixed still does not follow identical games across time buckets.</p>
    <div className="sc-controls">
      <label>Sport<select aria-label="State contrast sport" value={selectedSport?.sport || ""} onChange={event => chooseSport(event.target.value)}>{sports.map(item => <option key={item.sport} value={item.sport}>{sportLabel(item.sport)}</option>)}</select></label>
      <label>Adjacent time buckets<select aria-label="Adjacent time buckets" value={selectedPair?.id || ""} onChange={event => choosePair(event.target.value)}>{pairs.map(pair => <option key={pair.id} value={pair.id}>{pairLabel(pair.fromTime, pair.toTime)}</option>)}</select></label>
      <label>Same forecast band<select aria-label="Same forecast band" value={bandScope} onChange={event => setBandScope(event.target.value)}><option value="same">Same forecast band</option><option value="all">All forecast-band contrasts</option>{originBands.map(band => <option key={band} value={band}>Origin band {band}</option>)}</select></label>
      <label>Sort rows<select aria-label="Sort state contrasts" value={sort} onChange={event => setSort(event.target.value as "difference" | "support")}><option value="difference">Largest difference</option><option value="support">Minimum support</option></select></label>
    </div>
    {selectedSport && selectedPair ? <Figure source={SOURCE} asOf="published snapshot" title={`${sportLabel(selectedSport.sport)} bucket contrasts`} subtitle={`Each row compares published bucket populations from ${pairLabel(selectedPair.fromTime, selectedPair.toTime)}. The bar is scaled only within this selected time-pair.`} verdict="descriptive_only">
      {pairRows.length === 0 ? <p className="sc-empty">No published contrasts are available for this pair.</p> : <>
        {isFilteredEmpty && <p className="sc-filter-empty" role="status">{filterEmptyMessage}</p>}
        <div className="sc-compact-list" role="list" aria-label={`${sportLabel(selectedSport.sport)} compact state contrasts`}>
        {rows.map((row, index) => <article className="sc-compact-card" key={`${stateLabel(row, "from")}-${stateLabel(row, "to")}-${index}`} role="listitem">
          <p className="sc-compact-state">From state: {stateLabel(row, "from")}</p>
          <p className="sc-compact-values">Outcome frequency <span>{percent(row.from.meanOutcomeFrequency)}</span> | Forecast observations <span>{row.from.n.toLocaleString("en-US")}</span></p>
          <p className="sc-compact-state">To state: {stateLabel(row, "to")}</p>
          <p className="sc-compact-values">Outcome frequency <span>{percent(row.to.meanOutcomeFrequency)}</span> | Forecast observations <span>{row.to.n.toLocaleString("en-US")}</span></p>
          <p className={`sc-compact-delta ${deltaPercentagePoints(row.winprobDelta) < 0 ? "sc-delta-negative" : "sc-delta-positive"}`}>Difference <span>{percentagePoints(row.winprobDelta)}</span> | Minimum support <span>{row.minSupportN.toLocaleString("en-US")}</span></p>
        </article>)}
        </div>
        <button className="sc-full-table-control" type="button" aria-expanded={showFullTable} onClick={() => setShowFullTable(open => !open)}>Full table</button>
        <div className={`sc-table-wrap${showFullTable ? " sc-full-table-open" : ""}`} role="region" aria-label={`${sportLabel(selectedSport.sport)} state contrasts`} data-scroll-region>
        <table className="sc-table">
          <caption>Published contrasts from {selectedPair.fromTime} to {selectedPair.toTime}. Both state populations remain visible.</caption>
          <thead><tr><th scope="col">From state</th><th scope="col">Outcome frequency</th><th scope="col">Forecast observations</th><th scope="col">To state</th><th scope="col">Outcome frequency</th><th scope="col">Forecast observations</th><th scope="col">Difference</th><th scope="col">Minimum support</th></tr></thead>
          <tbody>{rows.map((row, index) => {
            const points = deltaPercentagePoints(row.winprobDelta);
            return <tr key={`${stateLabel(row, "from")}-${stateLabel(row, "to")}-${index}`}>
              <td>{stateLabel(row, "from")}</td><td>{percent(row.from.meanOutcomeFrequency)}</td><td>{row.from.n.toLocaleString("en-US")}</td>
              <td>{stateLabel(row, "to")}</td><td>{percent(row.to.meanOutcomeFrequency)}</td><td>{row.to.n.toLocaleString("en-US")}</td>
              <td><span className={`sc-delta ${points < 0 ? "sc-delta-negative" : "sc-delta-positive"}`}><i style={{ width: `${Math.abs(points) / scale * 100}%` }} />{percentagePoints(row.winprobDelta)}</span></td><td>{row.minSupportN.toLocaleString("en-US")}</td>
            </tr>;
          })}</tbody>
        </table>
        </div>
      </>}
    </Figure> : <p className="sc-empty">No published adjacent time buckets are available for this sport.</p>}
    <p className="sc-source-fields">Source fields: <span>public/data/showcase/why_attribution.json -&gt; sports.&lt;sport&gt;.transitions[] -&gt; from.time, from.prob, from.mean_y, from.n, to.time, to.prob, to.mean_y, to.n, winprob_delta, min_support_n</span>.</p>
  </section>;
}

export default StateContrasts;
