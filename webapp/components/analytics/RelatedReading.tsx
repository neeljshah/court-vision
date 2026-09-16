import Link from "next/link";
import { relatedReading, type ReadingKind } from "@/lib/analytics/related";

const labels: Record<ReadingKind, string> = { module: "Module", analysis: "Analysis", finding: "Finding" };
const sportLabel = (sport: string) => sport === "all" ? "Cross-sport" : sport.toUpperCase();

export function RelatedReading({ kind, id }: { kind: ReadingKind; id: string }) {
  const links = relatedReading(kind, id);
  if (!links.length) return null;
  const base = process.env.NEXT_PUBLIC_BASE_PATH || "";
  return <section className="related-reading" aria-label="Read next">
    <p className="overline">Read next</p>
    <div className="related-reading-grid">
      {links.map(link => <Link key={`${link.kind}-${link.id}`} href={`${base}${link.href}`} prefetch={false} className="related-reading-card">
        <span className="related-reading-kind">{labels[link.kind]}</span>
        <span className="serif related-reading-title">{link.title}</span>
        <span className="mono related-reading-meta">{sportLabel(link.sport)} {link.asOf ? `| as_of ${link.asOf.slice(0, 10)}` : "| as_of unrecorded"}</span>
      </Link>)}
    </div>
  </section>;
}
