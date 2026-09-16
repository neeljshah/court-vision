import Image from "next/image";
import { ArrowUpRight, BookOpen, FlaskConical } from "lucide-react";
import { base } from "@/lib/analytics/dashboardTypes";

export function WorkspaceIntro() {
  return <>
    <header className="cv-intro">
      <div className="cv-intro-copy">
        <p className="cv-eyebrow"><span className="cv-square" /> CourtVision / sports intelligence</p>
        <h1>Published sports<br /><span>measurements.</span></h1>
        <p>Compare matchups and player profiles, with each measurement linked to its published source.</p>
        <div className="cv-intro-actions">
          <a className="cv-primary" href={`${base}/analytics/browse/`}>Open the library <ArrowUpRight size={17} /></a>
          <a className="cv-intro-link" href={`${base}/analytics/evidence/`}>Source records <ArrowUpRight size={15} /></a>
        </div>
      </div>
      <figure className="cv-intro-art">
        <span className="cv-orbit cv-orbit-one" aria-hidden="true" />
        <span className="cv-orbit cv-orbit-two" aria-hidden="true" />
        <Image src={`${base}/brand/courtvision-emblem-hero.webp`} alt="CourtVision aperture emblem with an ascending orange path" width={640} height={640} sizes="(max-width: 620px) 82vw, (max-width: 920px) 56vw, 520px" priority unoptimized />
        <figcaption><span>Basketball, baseball, soccer and tennis.</span></figcaption>
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
