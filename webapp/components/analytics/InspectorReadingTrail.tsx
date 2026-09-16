import Link from "next/link";
import { analysisDestinations } from "@/lib/analytics/analysisDestinations";
import { noticesForInspector } from "@/lib/analytics/dataIntegrity";
import { bestPaperForInspector, paperBacklinks, readingEntries, relatedReadingFor } from "@/lib/analytics/related.server";
import { RelatedReadingLinks } from "./RelatedReading";
import { DataIntegrityNotice } from "./DataIntegrityNotice";

export function InspectorReadingTrail({ id }: { id: string }) {
  const inspector = analysisDestinations.find((destination) => destination.id === id);
  if (!inspector) return null;
  const prerequisite = inspector.prerequisiteId ? readingEntries().find((entry) => entry.id === inspector.prerequisiteId) : undefined;
  const next = inspector.nextId ? analysisDestinations.find((destination) => destination.id === inspector.nextId) : undefined;
  const paper = bestPaperForInspector(id);
  const backlinks = paperBacklinks("inspector", id);
  const links = [...backlinks, ...relatedReadingFor("inspector", id).filter((link) => !backlinks.some((backlink) => backlink.id === link.id && backlink.kind === link.kind)).slice(0, 3)];
  const integrityNotices = noticesForInspector(id);
  return <>
    <DataIntegrityNotice notices={integrityNotices} moduleIds={inspector.sourceModuleIds} />
    <section aria-label="Reading trail" style={{ margin: "18px 0 26px", paddingTop: 14, borderTop: "1px solid var(--rule)", color: "var(--ink-2)", fontSize: 14 }}>
    <p className="overline">Reading trail</p>
    {inspector.prerequisiteId ? <p style={{ marginTop: 6 }}>Read first: {prerequisite ? <Link href={prerequisite.href}>{inspector.prerequisite}</Link> : inspector.prerequisite}</p> : null}
    {next ? <p style={{ marginTop: 4 }}>Next question: <Link href={next.route}>{inspector.nextQuestion}</Link></p> : null}
    {paper ? <p style={{ marginTop: 4 }}>Read the analysis: <Link href={paper.href}>{paper.title}</Link></p> : null}
    {links.length ? <RelatedReadingLinks links={links} /> : null}
    </section>
  </>;
}
