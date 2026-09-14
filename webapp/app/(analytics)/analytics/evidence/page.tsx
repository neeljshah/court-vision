import type { Metadata } from "next";
import Image from "next/image";
import { EvidenceGallery } from "@/components/analytics/evidence/EvidenceGallery";
import { evidenceRepositoryUrl, getEvidenceCharts } from "@/lib/analytics/evidenceHub";
import "../workspace.css";
import "./evidence.css";

export const metadata: Metadata = {
  title: "Evidence & Platform",
  description: "A source-linked gallery of CourtVision's published visual evidence and documented platform architecture.",
};

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

export default function EvidencePage() {
  const charts = getEvidenceCharts();
  return <div className="cv-workspace evidence-page"><div className="cv-workspace-inner">
    <header className="evidence-hero"><div><p className="cv-eyebrow"><span className="cv-square" />CourtVision evidence</p><h1>Measurement, documentation, and the work behind them.</h1><p>Browse the public chart artifacts first, then follow their source modules and documentation in the public repository. The market-efficiency finding and documented limitations remain part of the record.</p><div className="evidence-doc-links"><a href={`${evidenceRepositoryUrl}/blob/master/docs/JOB_EVIDENCE_PACKET.md`} target="_blank" rel="noreferrer">Evidence packet</a><a href={`${evidenceRepositoryUrl}/blob/master/docs/PLATFORM.md`} target="_blank" rel="noreferrer">Platform documentation</a><a href={`${evidenceRepositoryUrl}/blob/master/docs/KNOWN_LIMITATIONS.md`} target="_blank" rel="noreferrer">Known limitations</a></div></div>
      <figure className="evidence-hero-visual"><Image unoptimized priority src={`${BASE_PATH}/brand/courtvision-research-fields.webp`} width={1672} height={941} decoding="async" alt="Abstract fields and data pathways" /><figcaption>Concept illustration</figcaption></figure>
    </header>
    <section className="evidence-flow" aria-labelledby="evidence-flow-title"><div><p className="cv-eyebrow"><span className="cv-square" />Architecture narrative</p><h2 id="evidence-flow-title">A documented path from footage to research artifacts</h2></div><ol><li><strong>Documented input</strong><span>NBA broadcast video and public sports data enter the repository's computer-vision and research pipeline.</span></li><li><strong>Documented processing</strong><span>Tracking, feature work, validation, and calibration produce dated research artifacts under recorded constraints.</span></li><li><strong>Published evidence</strong><span>This gallery exposes the chart artifacts that were staged for the public site, with links back to their modules.</span></li></ol></section>
    <section className="evidence-capabilities" aria-labelledby="capability-map-title"><div><p className="cv-eyebrow"><span className="cv-square" />Capability map</p><h2 id="capability-map-title">What is published, documented, and proposed</h2></div><div className="evidence-capability-grid"><article><span className="evidence-state published">Published</span><h3>Measurement workspace</h3><p>Current public page built from staged chart artifacts and a static site manifest.</p></article><article><span className="evidence-state documented">Documented</span><h3>CV and research pipeline</h3><p>Repository architecture and limitations are documented in the linked public records.</p></article><article><span className="evidence-state proposed">Proposed</span><h3>Hosted live backend</h3><p>Not represented here as an operating public service or live-status claim.</p></article><article><span className="evidence-state proposed">Proposed</span><h3>Validated new analytics</h3><p>Future analytics require their own published evidence before they appear in this gallery.</p></article></div></section>
    <EvidenceGallery charts={charts} />
  </div></div>;
}
