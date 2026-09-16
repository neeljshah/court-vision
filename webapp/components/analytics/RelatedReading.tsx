import Link from "next/link";
import type { ReadingKind, RelatedPurpose } from "@/lib/analytics/related";
import { paperBacklinks, relatedReadingFor } from "@/lib/analytics/related.server";

const labels: Record<ReadingKind, string> = { module: "Module", analysis: "Analysis", finding: "Finding", inspector: "Inspector", explainer: "Explainer", paper: "Paper" };
const purposeLabels: Record<RelatedPurpose, string> = { prerequisite: "Prerequisite", "same population": "Same population", "same entity type": "Same entity type", "same sport": "Same sport", "same source file": "Same source file", "supporting source": "Supporting source", "next question": "Next question" };
const sportLabel = (sport: string) => sport === "all" ? "Cross-sport" : sport.toUpperCase();

export function RelatedReadingLinks({ links }: { links: ReadonlyArray<{ id: string; title: string; kind: ReadingKind; sport: string; asOf: string | null; href: string; purpose: RelatedPurpose; prerequisite?: string }> }) {
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
  const backlinks = kind === "module" || kind === "inspector" ? paperBacklinks(kind, id) : [];
  const links = [...backlinks, ...relatedReadingFor(kind, id).filter((link) => !backlinks.some((backlink) => backlink.id === link.id && backlink.kind === link.kind))];
  if (!links.length) return null;
  return <section className="related-reading" aria-label="Read next">
    <p className="overline">Read next</p>
    <RelatedReadingLinks links={links} />
  </section>;
}
