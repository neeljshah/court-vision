import type { Metadata } from "next";
import Link from "next/link";
import { BlowoutTiming } from "@/components/analytics/blowout-timing/BlowoutTiming";
import { InspectorReadingTrail } from "@/components/analytics/InspectorReadingTrail";
import { Receipt } from "@/components/analytics/Receipt";
import { loadBlowoutTiming } from "@/lib/analytics/blowoutTiming.server";
import "./blowout-timing.css";

export const metadata: Metadata = {
  title: "Blowout timing",
  description: "Published frequency and conditional clock quartiles for permanent score margins.",
};

export default function BlowoutTimingPage() {
  const sports = loadBlowoutTiming();
  return <div className="bt-page">
    <p className="overline">Measurement / Blowout timing</p>
    <h1>Lasting leads by threshold.</h1>
    {!sports.length ? <>
      <InspectorReadingTrail id="blowout-timing" />
      <p className="bt-lede">The published blowout dynamics artifact is not available in this build.</p>
      <Link href="/analytics/browse/">Browse published modules</Link>
    </> : <>
    <p className="bt-lede">A threshold becomes permanent at the first recorded score tick from which the margin stays at or above that threshold through the last recorded score tick. This retrospective label is not predictable at the time. The artifact does not record whether that final tick is a complete final score.</p>
    <section className="bt-explanation" aria-labelledby="bt-reading">
      <h2 id="bt-reading">How to read the panels</h2>
      <p>Incidence reports the count and fraction of published games in which each threshold became permanent. Conditional timing reports the published P25, median, and P75 clock values only for those games. A usable game has at least the published parseable-tick floor, not a verified complete score. The source's decided_clockfrac_* fields divide the decided clock by the final observed clock, not verified regulation time. Masked rows retain their counts and the published mask state, but do not supply clock quartiles.</p>
    </section>
    <InspectorReadingTrail id="blowout-timing" />
    <BlowoutTiming sports={sports} />
    <p className="bt-source-fields">Source fields: <span className="mono">public/data/showcase/blowout_dynamics.json -&gt; sports.&lt;sport&gt;.unit, sports.&lt;sport&gt;.clock_field, sports.&lt;sport&gt;.n_games_raw, sports.&lt;sport&gt;.n_games_usable, sports.&lt;sport&gt;.min_ticks_floor, floors.min_games_per_threshold, sports.&lt;sport&gt;.thresholds[].threshold, sports.&lt;sport&gt;.thresholds[].n_games_total, sports.&lt;sport&gt;.thresholds[].n_games_decided, sports.&lt;sport&gt;.thresholds[].decided_frac_of_games, sports.&lt;sport&gt;.thresholds[].masked_below_floor, sports.&lt;sport&gt;.thresholds[].decided_clock_p25, sports.&lt;sport&gt;.thresholds[].decided_clock_median, sports.&lt;sport&gt;.thresholds[].decided_clock_p75</span>.</p>
    <div className="bt-receipt"><Receipt sourceArtifact="public/data/showcase/blowout_dynamics.json" label="descriptive_only" verdict="descriptive_only" /></div>
    </>}
  </div>;
}
