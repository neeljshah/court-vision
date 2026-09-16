"use client";
import { useId } from "react";
import { summarizeDistribution, type Distribution } from "@/lib/analytics/distribution";
import { displayMeasurement as display, type LabField, type LabRow } from "@/lib/analytics/labTypes";

export function DistributionSummary({ rows, field }: { rows: LabRow[]; field: LabField }) {
  const data = summarizeDistribution(rows, field.key);
  return <section className="distribution-summary" aria-label="Measurement summary">
    <dl>
      <div><dt>Measured rows</dt><dd>{data.measured}<small> / {data.total}</small><span>{data.missing} unavailable</span></dd></div>
      <div><dt>Median</dt><dd>{display(data.median, field)}<span>Middle ranked value</span></dd></div>
      <div><dt>Middle 50%</dt><dd className="distribution-interval">{data.measured ? `${display(data.q1, field)} to ${display(data.q3, field)}` : "Unavailable"}<span>25th to 75th percentile</span></dd></div>
      <div><dt>Observed range</dt><dd className="distribution-interval">{data.measured ? `${display(data.min, field)} to ${display(data.max, field)}` : "Unavailable"}<span>Minimum to maximum</span></dd></div>
    </dl>
    <p>Summaries describe the filtered rows with equal row weight. Row counts are not independent game or event counts.</p>
  </section>;
}

function BinDetails({ data, field }: { data: Distribution; field: LabField }) {
  return <details className="distribution-method"><summary>Bin counts and calculation</summary>
    <div className="cv-table-scroll" role="region" tabIndex={0} aria-label="Distribution bin table"><table className="cv-benchmark-table"><caption>{field.label}: histogram counts</caption><thead><tr><th scope="col">Measurement interval</th><th scope="col">Rows</th><th scope="col">Share of measured rows</th></tr></thead><tbody>{data.bins.map((bin, i) => <tr key={i}><th scope="row">{bin.low === bin.high ? display(bin.low, field) : `${display(bin.low, field)} to ${bin.includesHigh ? "and including" : "below"} ${display(bin.high, field)}`}</th><td>{bin.count}</td><td>{(100 * bin.count / data.measured).toFixed(1)}%</td></tr>)}</tbody></table></div>
    <p>Each bin includes its lower boundary. Only the last bin includes its upper boundary. Labels are rounded; counts use unrounded values. Bin count is the square root of measured rows, rounded up, capped at eight; constant values use one bin.</p>
    <p>Quartiles use linear interpolation at p(n - 1), the R7 method. Each published row has equal weight. These summaries are descriptive, without confidence intervals or population inference.</p>
    <div className="distribution-method-links"><a href="https://www.itl.nist.gov/div898/handbook/eda/section3/histogra.htm" target="_blank" rel="noreferrer">Histogram method</a><a href="https://www.itl.nist.gov/div898/handbook/prc/section2/prc262.htm" target="_blank" rel="noreferrer">Percentile definitions</a></div>
  </details>;
}

export function DistributionPlot({ rows, field }: { rows: LabRow[]; field: LabField }) {
  const data = summarizeDistribution(rows, field.key), id = useId();
  if (!data.measured) return <div className="cv-empty">No numeric measurements are available for a distribution. Missing values remain in the data table.</div>;
  const maximum = Math.max(...data.bins.map(bin => bin.count));
  const spreadField: LabField = field.unit === "percent" ? { ...field, unit: "pp" } : field;
  return <section className="distribution-plot" aria-label="Measurement distribution">
    <div className="distribution-plot-heading"><div><p className="cv-eyebrow">Distribution / {field.label}</p><h3>Where the measurements fall.</h3></div><span>{data.measured} measured {data.measured === 1 ? "row" : "rows"}</span></div>
    <p id={id} className="distribution-description">{data.min === data.max ? `Every measured row has the same value: ${display(data.min, field)}.` : `The middle 50% runs from ${display(data.q1, field)} to ${display(data.q3, field)}. The median is ${display(data.median, field)}.`}</p>
    <figure aria-describedby={id}><div className="distribution-bars" role="img" aria-label={`${field.label} histogram, ${data.bins.length} bins. Exact bin counts follow in the expandable table.`}>{data.bins.map((bin, i) => <div key={i} className="distribution-bin" aria-hidden="true"><span style={{ bottom: `calc(${bin.count / maximum * 100}% + 5px)` }}>{bin.count}</span><i style={{ height: `${bin.count / maximum * 100}%` }} /></div>)}</div><figcaption><span>{display(data.min, field)}</span><span>Bar height = row count</span><span>{display(data.max, field)}</span></figcaption></figure>
    <div className="distribution-breakdown"><span>Mean <b>{display(data.mean, field)}</b></span><span>Interquartile range <b>{display(data.iqr, spreadField)}</b></span><span>Below zero <b>{data.negative}</b></span><span>Zero <b>{data.zero}</b></span><span>Above zero <b>{data.positive}</b></span></div>
    <BinDetails data={data} field={field} />
  </section>;
}
