import Link from "next/link";
import { analysisDestinations } from "@/lib/analytics/analysisDestinations";
import { readingCollections } from "@/lib/analytics/readingCollections";
import { relatedReading, readingEntries } from "@/lib/analytics/related";
import { RelatedReadingLinks } from "./RelatedReading";

const ignoredWords = new Set(["the", "and", "before", "read", "first", "this", "that", "with", "from", "into", "their"]);
const readingWords = (value: string) => value.toLowerCase().match(/[a-z0-9]{3,}/g)?.filter((word) => !ignoredWords.has(word)) || [];

function prerequisiteTarget(prerequisite: string, selfId: string) {
  // ponytail: word overlap on titles; readings (inspectors, findings, explainers) win over raw source modules
  const terms = new Set(readingWords(prerequisite));
  const scored = readingEntries().filter((entry) => entry.id !== selfId)
    .map((entry) => ({ entry, score: readingWords(entry.title).filter((word) => terms.has(word)).length }))
    .filter(({ score }) => score > 0)
    .sort((left, right) => Number(right.entry.kind !== "module") - Number(left.entry.kind !== "module") || right.score - left.score || left.entry.title.localeCompare(right.entry.title));
  return scored[0]?.entry;
}

function nextInspector(id: string) {
  const collection = readingCollections.find((item) => item.members.some((member) => member.kind === "inspector" && member.id === id));
  const current = collection?.members.findIndex((member) => member.kind === "inspector" && member.id === id) ?? -1;
  const nextId = current < 0 ? undefined : collection?.members.slice(current + 1).find((member) => member.kind === "inspector")?.id;
  return analysisDestinations.find((destination) => destination.id === nextId);
}

export function InspectorReadingTrail({ id }: { id: string }) {
  const inspector = analysisDestinations.find((destination) => destination.id === id);
  if (!inspector) return null;
  const prerequisite = prerequisiteTarget(inspector.prerequisite, id), next = nextInspector(id), links = relatedReading("inspector", id).slice(0, 3);
  return <section aria-label="Reading trail" style={{ margin: "18px 0 26px", paddingTop: 14, borderTop: "1px solid var(--rule)", color: "var(--ink-2)", fontSize: 14 }}>
    <p className="overline">Reading trail</p>
    <p style={{ marginTop: 6 }}>Read first: {prerequisite ? <Link href={prerequisite.href}>{inspector.prerequisite}</Link> : inspector.prerequisite}</p>
    {next ? <p style={{ marginTop: 4 }}>Next question: <Link href={next.route}>{inspector.nextQuestion}</Link></p> : null}
    {links.length ? <RelatedReadingLinks links={links} /> : null}
  </section>;
}
