import Image from "next/image";
import { ArrowUpRight, BookOpen, FlaskConical, Users } from "lucide-react";
import { base } from "@/lib/analytics/dashboardTypes";

export function WorkspaceIntro() {
  return <>
    <header className="cv-intro">
      <div className="cv-intro-copy">
        <p className="cv-eyebrow"><span className="cv-square" /> The CourtVision research desk</p>
        <h1>See the game.<br /><span>Understand the evidence.</span></h1>
        <p>Four sports. Open research. Explore the patterns behind performance, with the measurements to back them up.</p>
        <div className="cv-intro-actions">
          <a className="cv-primary" href={`${base}/analytics/ask/`}>Ask Scout <ArrowUpRight size={17} /></a>
          <a className="cv-intro-link" href={`${base}/analytics/evidence/`}>Explore the evidence <ArrowUpRight size={15} /></a>
        </div>
      </div>
      <figure className="cv-intro-art">
        <Image src={`${base}/brand/courtvision-research-fields.webp`} alt="An illustrated basketball court, baseball diamond, soccer field, and tennis court" width={1672} height={941} priority unoptimized />
        <figcaption>Four sports. One research workspace. <span>Concept illustration</span></figcaption>
      </figure>
    </header>
    <nav className="cv-launch" aria-label="Explore deeper">
      <a href={`${base}/analytics/lab/`}><FlaskConical size={17} /><strong>Measurement lab</strong><span>Rank, plot & inspect</span><ArrowUpRight size={15} /></a>
      <a href={`${base}/analytics/compare/`}><Users size={17} /><strong>Compare profiles</strong><span>Find the differences</span><ArrowUpRight size={15} /></a>
      <a href={`${base}/analytics/evidence/`}><BookOpen size={17} /><strong>Evidence gallery</strong><span>Follow the results</span><ArrowUpRight size={15} /></a>
    </nav>
  </>;
}
