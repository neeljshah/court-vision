"use client";

import { useEffect, useState } from "react";
import { linePath, linear, type Pt } from "@/components/analytics/charts/scale";
import type { ReliabilityBin, ReliabilitySeries, ReliabilitySide } from "@/lib/analytics/calibrationReliability";

type SeriesChoice = ReliabilitySide | "both";
type BinRange = { lo: number; hi: number } | null;
const sides: ReliabilitySide[] = ["model", "market"];
const labels: Record<ReliabilitySide, string> = { model: "Model", market: "Market" };
const colors: Record<ReliabilitySide, string> = { model: "var(--accent)", market: "var(--signal)" };
const PAD = { left: 48, right: 18, top: 24, bottom: 44 };
const TICKS = [0, 0.25, 0.5, 0.75, 1];

function sportLabel(sport: string): string {
  return sport === "mlb" ? "MLB" : sport === "soccer_intl" ? "International soccer" : sport.replace(/_/g, " ");
}

function percent(value: number | null, digits = 1): string {
  return value === null ? "Not published" : `${(value * 100).toFixed(digits)}%`;
}

function percentagePoints(value: number | null): string {
  return value === null ? "Not published" : `${(value * 100).toFixed(2)} pp`;
}

function count(value: number | null): string {
  return value === null ? "Not published" : value.toLocaleString("en-US");
}

function interval(value: readonly [number | null, number | null]): string {
  return value[0] === null || value[1] === null ? "Not published" : `${percent(value[0])} to ${percent(value[1])}`;
}

function gapInterval(value: readonly [number | null, number | null]): string {
  return value[0] === null || value[1] === null ? "Not published" : `${percentagePoints(value[0])} to ${percentagePoints(value[1])}`;
}

function decimal(value: number | null): string {
  return value === null ? "Not published" : value.toFixed(6);
}

function validPoint(bin: ReliabilityBin): bin is ReliabilityBin & { meanP: number; meanY: number } {
  return bin.meanP !== null && bin.meanY !== null;
}

function readState(series: ReliabilitySeries[]): { sport: string; choice: SeriesChoice; binRange: BinRange } {
  const params = new URLSearchParams(window.location.search);
  const requestedSport = params.get("sport");
  const sport = series.some(item => item.sport === requestedSport) ? requestedSport! : series[0]?.sport || "";
  const requestedChoice = params.get("series");
  const choice: SeriesChoice = requestedChoice === "model" || requestedChoice === "market" || requestedChoice === "both" ? requestedChoice : "both";
  const requestedBinLo = params.get("bin_lo");
  const requestedBinHi = params.get("bin_hi");
  const binLo = Number(requestedBinLo);
  const binHi = Number(requestedBinHi);
  const binRange = requestedBinLo !== null && requestedBinHi !== null && Number.isFinite(binLo) && Number.isFinite(binHi) ? { lo: binLo, hi: binHi } : null;
  return { sport, choice, binRange };
}

function matchesBinRange(bin: ReliabilityBin, range: BinRange): boolean {
  return range !== null && bin.binLo === range.lo && bin.binHi === range.hi;
}

export function CalibrationReliability({ series }: { series: ReliabilitySeries[] }) {
  const sports = Array.from(new Set(series.map(item => item.sport)));
  const [sport, setSport] = useState(sports[0] || "");
  const [choice, setChoice] = useState<SeriesChoice>("both");
  const [binRange, setBinRange] = useState<BinRange>(null);
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    const restore = () => {
      const next = readState(series);
      setSport(next.sport);
      setChoice(next.choice);
      setBinRange(next.binRange);
      setRestored(true);
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [series]);

  useEffect(() => {
    if (!restored) return;
    const url = new URL(window.location.href);
    url.searchParams.set("sport", sport);
    url.searchParams.set("series", choice);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }, [choice, restored, sport]);

  const selected = series.filter(item => item.sport === sport && (choice === "both" || item.side === choice));
  const corpus = selected[0]?.meta;
  const allN = selected.flatMap(item => item.bins.map(bin => bin.n).filter((n): n is number => n !== null));
  const maxN = Math.max(...allN, 1);
  const width = 620;
  const plot = 500;
  const height = PAD.top + PAD.bottom + plot;
  const sx = linear(0, 1, PAD.left, PAD.left + plot);
  const sy = linear(0, 1, PAD.top + plot, PAD.top);
  const radius = (n: number | null) => 3 + 5 * Math.sqrt((n || 0) / maxN);

  if (!sports.length) return <p className="cr-empty">No published reliability bins are available in this snapshot.</p>;

  return <section className="cr-shell" aria-label="Reliability bin inspector">
    <div className="cr-controls">
      <label>Sport<select aria-label="Reliability sport" value={sport} onChange={event => setSport(event.target.value)}>{sports.map(item => <option key={item} value={item}>{sportLabel(item)}</option>)}</select></label>
      <div className="cr-toggle" aria-label="Reliability series">{(["both", ...sides] as SeriesChoice[]).map(item => <button key={item} type="button" aria-pressed={choice === item} onClick={() => setChoice(item)}>{item === "both" ? "Both" : labels[item]}</button>)}</div>
    </div>
    {corpus && <p className="cr-corpus"><strong>{sportLabel(sport)}:</strong> {count(corpus.nRows)} ticks from {count(corpus.nGames)} games; ticks are not independent games.{corpus.lowPower ? " This corpus is flagged low power." : ""}</p>}
    <div className="cr-legend"><span><i className="cr-diagonal" />Perfect calibration</span>{selected.map(item => <span key={item.side}><i style={{ background: colors[item.side] }} />{labels[item.side]}</span>)}<span><i className="cr-hollow" />Low-n bin</span></div>
    <div className="cr-chart-wrap" role="region" aria-label="Reliability diagram (scrollable)" tabIndex={0}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${sportLabel(sport)} reliability diagram`} data-testid="reliability-diagram">
        <line x1={PAD.left} x2={PAD.left + plot} y1={PAD.top + plot} y2={PAD.top} className="cr-reference" />
        {TICKS.map(tick => <g key={tick}>
          <line x1={sx(tick)} x2={sx(tick)} y1={PAD.top} y2={PAD.top + plot} className="cr-grid" />
          <line x1={PAD.left} x2={PAD.left + plot} y1={sy(tick)} y2={sy(tick)} className="cr-grid" />
          <text x={sx(tick)} y={PAD.top + plot + 21} textAnchor="middle">{Math.round(tick * 100)}%</text>
          <text x={PAD.left - 9} y={sy(tick) + 4} textAnchor="end">{Math.round(tick * 100)}%</text>
        </g>)}
        <text className="cr-axis" x={PAD.left + plot / 2} y={height - 5} textAnchor="middle">Mean forecast probability</text>
        <text className="cr-axis" x={-(PAD.top + plot / 2)} y={13} transform="rotate(-90)" textAnchor="middle">Observed frequency</text>
        {selected.map(item => {
          const points: Pt[] = item.bins.filter(validPoint).map(bin => ({ x: bin.meanP, y: bin.meanY }));
          return <g key={item.side} className={`cr-series cr-${item.side}`}>
            <path d={linePath(points, sx, sy)} fill="none" stroke={colors[item.side]} strokeWidth="2" />
            {item.bins.filter(validPoint).map((bin, index) => {
              const [low, high] = bin.meanYCi;
              const hasCi = low !== null && high !== null;
              return <g key={index} opacity={0.45 + 0.55 * Math.sqrt((bin.n || 0) / maxN)}>
                {hasCi && <><line x1={sx(bin.meanP)} x2={sx(bin.meanP)} y1={sy(low)} y2={sy(high)} stroke={colors[item.side]} strokeWidth="1.25" /><line x1={sx(bin.meanP) - 4} x2={sx(bin.meanP) + 4} y1={sy(low)} y2={sy(low)} stroke={colors[item.side]} /><line x1={sx(bin.meanP) - 4} x2={sx(bin.meanP) + 4} y1={sy(high)} y2={sy(high)} stroke={colors[item.side]} /></>}
                <circle cx={sx(bin.meanP)} cy={sy(bin.meanY)} r={radius(bin.n)} fill={bin.lowN ? "var(--paper-raised)" : colors[item.side]} stroke={colors[item.side]} strokeWidth={bin.lowN ? 2 : 1}><title>{`${labels[item.side]} ${percent(bin.meanP)} forecast, ${percent(bin.meanY)} observed, ${percentagePoints(bin.gap)} gap, ${count(bin.n)} ticks`}</title></circle>
              </g>;
            })}
          </g>;
        })}
      </svg>
    </div>
    <div className="cr-worked-examples" aria-live="polite">
      {selected.map(item => {
        const bin = item.bins.find(candidate => matchesBinRange(candidate, binRange)) || item.bins[0];
        if (!bin) return null;
        return <article key={item.side} className="cr-worked-example">
          <p className="cr-worked-label">{sportLabel(sport)} / {labels[item.side]} worked example</p>
          <h3>{percent(bin.binLo, 0)} to {percent(bin.binHi, 0)} probability bin</h3>
          <p>Mean forecast {percent(bin.meanP)} and observed frequency {percent(bin.meanY)} produce a published {percentagePoints(bin.gap)} gap. The observed-frequency interval is {interval(bin.meanYCi)}.</p>
          <dl><div><dt>Eligible bins</dt><dd>{count(item.diagnostics.nEligibleBins)}</dd></div><div><dt>Significant bins</dt><dd>{count(item.diagnostics.nSignificantBins)}</dd></div><div><dt>Within noise</dt><dd>{count(item.diagnostics.nWithinNoiseBins)}</dd></div><div><dt>Published Brier</dt><dd>{decimal(item.diagnostics.brier)}</dd></div></dl>
        </article>;
      })}
    </div>
    <div className="cr-table-wrap" role="region" aria-label="Reliability bins" data-scroll-region>
      <table className="cr-table"><caption>Published reliability bins for {sportLabel(sport)}</caption><thead><tr><th>Series</th><th>Bin range</th><th>Mean forecast</th><th>Observed</th><th>Gap (pp)</th><th>Gap CI (pp)</th><th>n ticks</th><th>n games</th><th>Low n</th></tr></thead><tbody>{selected.flatMap(item => item.bins.map((bin, index) => <tr key={`${item.side}-${index}`}><td><span className={`cr-series-key cr-${item.side}`} />{labels[item.side]}</td><td>{percent(bin.binLo, 0)} to {percent(bin.binHi, 0)}</td><td>{percent(bin.meanP)}</td><td>{percent(bin.meanY)}</td><td>{percentagePoints(bin.gap)}</td><td>{gapInterval(bin.gapCi)}</td><td>{count(bin.n)}</td><td>{count(bin.nGames)}</td><td>{bin.lowN ? "Yes" : "No"}</td></tr>))}</tbody></table>
    </div>
  </section>;
}

export default CalibrationReliability;
