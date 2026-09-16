import manifest from "@/public/data/showcase/site_manifest.json";

const SPORTS = [
  ["Basketball", /\bnba\b|\bwnba\b/i],
  ["Baseball", /\bmlb\b|baseball|statcast/i],
  ["Soccer", /\bsoccer\b/i],
  ["Tennis", /\btennis\b/i],
] as const;

function publishedLedger() {
  const records = manifest.modules.map((module) => JSON.stringify(module));
  const sports = SPORTS.filter(([, pattern]) => records.some((record) => pattern.test(record))).map(([sport]) => sport);
  const dates = manifest.modules.flatMap((module) => module.as_of?.match(/\d{4}-\d{2}-\d{2}/g) ?? []).sort();

  return {
    chartCount: manifest.modules.filter((module) => module.chart_path).length,
    dateRange: `${dates[0]} to ${dates[dates.length - 1]}`,
    moduleCount: manifest.module_count,
    sports,
  };
}

export function PipelineLedger() {
  const ledger = publishedLedger();

  return <section className="pipeline-ledger" aria-labelledby="pipeline-ledger-title">
    <div className="pipeline-ledger-heading">
      <p className="cv-eyebrow"><span className="cv-square" />Published snapshot</p>
      <h2 id="pipeline-ledger-title">Pipeline ledger</h2>
      <p>Counts are read from the committed site manifest, not a live service.</p>
    </div>
    <ol className="pipeline-ledger-flow">
      <li><strong>Inputs</strong><span>{ledger.sports.join(", ")}</span></li>
      <li><strong>Processing</strong><span>{ledger.moduleCount} documented modules</span></li>
      <li><strong>Published artifacts</strong><span>{ledger.chartCount} chart-backed records</span></li>
    </ol>
    <dl className="pipeline-ledger-stats">
      <div><dt>Sports covered</dt><dd>{ledger.sports.length}</dd></div>
      <div><dt>As-of range</dt><dd>{ledger.dateRange}</dd></div>
    </dl>
    <a className="pipeline-ledger-link" href="#published-gallery">View the {ledger.chartCount} published charts</a>
  </section>;
}
