import Link from "next/link";
import { relatedReading, type ReadingKind, type RelatedPurpose } from "@/lib/analytics/related";

const labels: Record<ReadingKind, string> = { module: "Module", analysis: "Analysis", finding: "Finding", inspector: "Inspector", explainer: "Explainer" };
const purposeLabels: Record<RelatedPurpose, string> = { prerequisite: "Prerequisite", "same population": "Same population", "same entity type": "Same entity type", "same sport": "Same sport", "same source file": "Same source file", "supporting source": "Supporting source", "next question": "Next question" };
const sportLabel = (sport: string) => sport === "all" ? "Cross-sport" : sport.toUpperCase();

export function RelatedReadingLinks({ links }: { links: ReturnType<typeof relatedReading> }) {
  return <div className="related-reading-grid">
    {links.map(link => <Link key={`${link.kind}-${link.id}`} href={link.href} prefetch={false} className="related-reading-card">
      <span className="related-reading-kind">{labels[link.kind]}</span><span className="related-reading-purpose" style={{ alignSelf: "flex-start", border: "1px solid var(--rule)", borderRadius: "var(--radius-chip)", color: "var(--ink-3)", fontSize: 10, padding: "1px 6px" }}>{purposeLabels[link.purpose]}</span>
      <span className="serif related-reading-title">{link.title}</span>
      <span className="mono related-reading-meta">{sportLabel(link.sport)} {link.asOf ? `| as_of ${link.asOf.slice(0, 10)}` : "| as_of unrecorded"}</span>
      {link.kind === "inspector" && link.prerequisite ? <span className="mono related-reading-meta">Prerequisite: {link.prerequisite}</span> : null}
    </Link>)}
  </div>;
}

export function RelatedReading({ kind, id }: { kind: ReadingKind; id: string }) {
  const links = relatedReading(kind, id);
  if (!links.length) return null;
  return <section className="related-reading" aria-label="Read next">
    <p className="overline">Read next</p>
    <RelatedReadingLinks links={links} />
  </section>;
}
