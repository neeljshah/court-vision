import { metricLabel, type ComparisonPack } from "@/lib/analytics/comparisonData";

export function ComparableContext({ pack }: { pack: ComparisonPack }) {
  const context = pack.comparableContext;
  if (!context) return null;
  if (context.skipped) {
    return <section className="comparable-context" aria-labelledby="comparable-context-title"><span className="compare-section-label">Published comparables</span><h2 id="comparable-context-title">How similarity is measured</h2><p>{pack.key.replace(/_/g, " ")}: {context.skipped.nCommonFields} common fields, no comparables published.</p><p>Published reason: {context.skipped.reason}.</p><p>Population: {pack.nInPack} profiles.</p></section>;
  }
  const corpusLengthFields = pack.key === "nba_players" ? context.fieldsUsed.filter((field) => ["career_games", "career_minutes", "seasons_played"].includes(field)) : [];
  return <section className="comparable-context" aria-labelledby="comparable-context-title"><span className="compare-section-label">Published comparables</span><h2 id="comparable-context-title">How similarity is measured</h2><p>{context.method || "No published similarity method is available for this pack."}</p><dl><div><dt>Fields used</dt><dd>{context.fieldsUsed.length ? <ul>{context.fieldsUsed.map((field) => <li key={field}>{metricLabel(field)}</li>)}</ul> : "No fields were published."}</dd></div><div><dt>Dropped fields</dt><dd>{context.droppedZeroVariance.length ? context.droppedZeroVariance.map(metricLabel).join(", ") : "No zero-variance fields were dropped."}</dd></div><div><dt>Population</dt><dd>{pack.nInPack} profiles.</dd></div></dl>{corpusLengthFields.length ? <p>For NBA players, corpus length is part of the distance through {corpusLengthFields.map(metricLabel).join(", ")}.</p> : null}<p>The score describes distance across these fields. It is not a probability or a quality rating.</p></section>;
}
