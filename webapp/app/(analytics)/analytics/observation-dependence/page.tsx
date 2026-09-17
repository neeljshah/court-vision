import type { Metadata } from "next";
import Link from "next/link";
import { ObservationDependence } from "@/components/analytics/observation-dependence/ObservationDependence";
import { InspectorReadingTrail } from "@/components/analytics/InspectorReadingTrail";
import { Receipt } from "@/components/analytics/Receipt";
import { buildObservationDependence } from "@/lib/analytics/observationDependence";
import { loadArtifact, type Artifact } from "@/lib/showcase.server";
import "./observation-dependence.css";

export const metadata: Metadata = {
  title: "Observation dependence",
  description: "Published within-game lag-1 residual autocorrelation distributions, shown separately for model and market series.",
};

type DependenceArtifact = Omit<Artifact, "floors" | "generated_at" | "as_of"> & {
  floors?: { min_rows_per_game?: number; min_residual_variance?: number };
  generated_at?: string | null;
  as_of?: string | null;
};

export default function ObservationDependencePage() {
  const data = loadArtifact("residual_autocorrelation") as DependenceArtifact | null;
  const sports = buildObservationDependence(data);
  const floors = data?.floors;
  return <div className="od-page">
    <p className="overline">Measurement / Observation dependence</p>
    <h1>Repeated ticks are not repeated evidence.</h1>
    {!data || !sports.length ? <>
      <InspectorReadingTrail id="observation-dependence" />
      <p className="od-lede">The published residual-autocorrelation exhibit is not available in this build.</p>
      <Link href="/analytics/browse/">Browse published modules</Link>
    </> : <>
    <p className="od-lede">This exhibit makes the dependence behind in-game calibration measurements visible. It reads <span className="mono">residual_autocorrelation.json -&gt; sports.&lt;sport&gt;.autocorr_values.&#123;model, market&#125;[]</span>, retaining the model and market arrays as separate populations.</p>
    <section className="od-explanation" aria-labelledby="od-meaning">
      <h2 id="od-meaning">What the measure says</h2>
      <p>Lag-1 residual autocorrelation compares each within-game signed residual with the one immediately before it. A value near 1 means consecutive ticks carry almost the same information: the probability path changes smoothly while the terminal outcome stays fixed.</p>
      <p>The site reports ticks and games because they answer different questions. Ticks describe how often the system was observed; games describe the independent units behind a calibration measurement. This page does not infer an exact effective sample size. See the <Link href="/analytics/findings/effective-sample-size">effective-sample-size finding</Link> and the <Link href="/analytics/calibration">calibration page</Link> for their published context.</p>
      <p className="od-floors">Eligibility floors: at least {floors?.min_rows_per_game ?? "the published minimum"} rows per game and residual variance of at least {floors?.min_residual_variance ?? "the published minimum"}. Exclusions are shown by side below.</p>
    </section>
    <InspectorReadingTrail id="observation-dependence" />
    <ObservationDependence sports={sports} asOf={data.generated_at || data.as_of || undefined} dateKind={data.generated_at ? "snapshot" : "source"} />
    <div className="od-receipt"><Receipt sourceArtifact="public/data/showcase/residual_autocorrelation.json" asOf={data.generated_at || data.as_of || undefined} dateKind={data.generated_at ? "snapshot" : "source"} label="descriptive_only" verdict="descriptive_only" /></div>
    </>}
  </div>;
}
