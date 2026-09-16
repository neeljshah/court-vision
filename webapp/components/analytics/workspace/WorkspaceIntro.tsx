import Image from "next/image";
import Link from "next/link";
import { ArrowUpRight, BookOpen, FlaskConical } from "lucide-react";
import { base } from "@/lib/analytics/dashboardTypes";
import type { HomeCalibrationExample } from "@/lib/analytics/homeCalibrationExample";

function percentage(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function binPercentage(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

function percentile(value: number): string {
  return `${value.toFixed(1).replace(/\.0$/, "")}%`;
}

function clusterLabel(value: string): string {
  return value.replace(/_id$/, "").replace(/_/g, " ");
}

export function WorkspaceIntro({ example }: { example: HomeCalibrationExample | null }) {
  return <>
    <header className="cv-intro">
      <div className="cv-intro-copy">
        <p className="cv-eyebrow"><span className="cv-square" /> CourtVision / forecast calibration</p>
        <h1>How forecasts<br /><span>compare with outcomes.</span></h1>
        {example ? <section className="cv-calibration-example" role="region" aria-label="Published MLB calibration example">
          {example.integrity_status === "regenerated" ? <p style={{ color: "var(--signal-ink)", fontWeight: 600, marginBottom: 12 }}>These MLB/soccer numbers are revision 2, computed on the segment-clean corpus (2026-09-16). Revision 1 values are withdrawn and kept in the regeneration receipt. <Link href="/analytics/findings/ingame-join-integrity/">Read the finding.</Link></p> : null}
          <p>For MLB, model forecasts of <strong>{binPercentage(example.bin_lo)} to {binPercentage(example.bin_hi)}</strong>, the mean forecast was <strong>{percentage(example.mean_p)}</strong> and the observed frequency was <strong>{percentage(example.mean_y)}</strong>, from <strong>{example.n.toLocaleString("en-US")}</strong> observations across <strong>{example.n_games.toLocaleString("en-US")}</strong> games. Snapshot date: <strong>{example.artifact_date || "Date not published."}</strong>{example.artifact_date ? "." : ""}</p>
          <div className="cv-calibration-bars" role="img" aria-label={`Forecast mean ${percentage(example.mean_p)} and observed frequency ${percentage(example.mean_y)}`}>
            <div><span>Forecast mean</span><strong>{percentage(example.mean_p)}</strong><i style={{ width: percentage(example.mean_p) }} /></div>
            <div><span>Observed frequency</span><strong>{percentage(example.mean_y)}</strong><i style={{ width: percentage(example.mean_y) }} /></div>
          </div>
          <p className="cv-calibration-interval">Observed-frequency interval: {percentage(example.mean_y_ci[0])} to {percentage(example.mean_y_ci[1])} ({(example.ci_pct[1] - example.ci_pct[0]).toFixed(2)}% {clusterLabel(example.cluster_unit)}-cluster bootstrap interval; {percentile(example.ci_pct[0])} to {percentile(example.ci_pct[1])} percentiles; {example.n_boot.toLocaleString("en-US")} resamples).</p>
          <p>The published gap is <strong>{(example.gap * 100).toFixed(2)} percentage points</strong>; its interval is <strong>{(example.gap_ci[0] * 100).toFixed(2)} to {(example.gap_ci[1] * 100).toFixed(2)} percentage points</strong>, includes zero, and does not establish agreement.</p>
          <Link className="cv-calibration-link" href={`/analytics/calibration?sport=mlb&series=model&bin_lo=${example.bin_lo}&bin_hi=${example.bin_hi}`}>Inspect this exact calibration bin <ArrowUpRight size={13} /></Link>
        </section> : <p className="cv-calibration-unavailable">The published calibration example is unavailable in this snapshot.</p>}
        <nav className="cv-reading-sequence" aria-label="Read calibration sequence">
          <a href={`${base}/analytics/calibration/`}>Reliability <ArrowUpRight size={13} /></a>
          <a href={`${base}/analytics/observation-dependence/`}>Repeated observations <ArrowUpRight size={13} /></a>
          <a href={`${base}/analytics/state-reliability/`}>State reliability <ArrowUpRight size={13} /></a>
        </nav>
      </div>
      <figure className="cv-intro-art">
        <span className="cv-orbit cv-orbit-one" aria-hidden="true" />
        <span className="cv-orbit cv-orbit-two" aria-hidden="true" />
        <Image src={`${base}/brand/courtvision-emblem-hero.webp`} alt="CourtVision aperture emblem with an ascending orange path" width={640} height={640} sizes="(max-width: 620px) 210px, (max-width: 920px) 45vw, 330px" priority unoptimized />
        <figcaption><span>Published calibration snapshot.</span></figcaption>
      </figure>
    </header>
    <nav className="cv-launch" aria-label="Explore published sports and research">
      <a href={`${base}/analytics/compare/?pack=nba_players`}><small>01</small><strong>NBA</strong><span>Player profiles</span><ArrowUpRight size={15} /></a>
      <a href={`${base}/analytics/compare/?pack=mlb_batters`}><small>02</small><strong>MLB</strong><span>Batter profiles</span><ArrowUpRight size={15} /></a>
      <a href={`${base}/analytics/compare/?pack=soccer`}><small>03</small><strong>Soccer</strong><span>Team profiles</span><ArrowUpRight size={15} /></a>
      <a href={`${base}/analytics/compare/?pack=tennis`}><small>04</small><strong>Tennis</strong><span>Player profiles</span><ArrowUpRight size={15} /></a>
      <a href={`${base}/analytics/lab/`}><FlaskConical size={16} /><strong>Lab</strong><span>Inspect measurements</span><ArrowUpRight size={15} /></a>
      <a href={`${base}/analytics/evidence/`}><BookOpen size={16} /><strong>Research</strong><span>View sources</span><ArrowUpRight size={15} /></a>
    </nav>
  </>;
}
