// One research paper, hand-set as an editorial reading column: numbered sections, an
// in-page table of contents, an evidence box that names every cited artifact and field
// path, the limitations the paper accepts, and the related readings it points at.
import Link from "next/link";
import { PaperBlockView } from "./PaperBlocks";
import { resolveRelated } from "@/lib/analytics/papers.server";
import { readingMinutes, SPORT_LABELS, type Paper, type PaperBlock } from "@/lib/analytics/papers";
import { noticesForPaper } from "@/lib/analytics/dataIntegrity";
import { DataIntegrityNotice } from "@/components/analytics/DataIntegrityNotice";

const kindLabels: Record<string, string> = {
  inspector: "Inspector", analysis: "Analysis", module: "Source module", paper: "Paper",
};

function EvidenceBox({ paper }: { paper: Paper }) {
  return (
    <section className="paper-box" aria-labelledby="paper-evidence">
      <h2 id="paper-evidence">Evidence</h2>
      <ol className="paper-evidence">
        {paper.evidence.map(entry => (
          <li key={`${entry.artifact}-${entry.module}`}>
            <span className="mono paper-artifact">{entry.artifact}</span>
            <span className="paper-note">{entry.asOf ? `as_of ${entry.asOf}` : "date not published"}</span>
            <Link href={`/analytics/m/${entry.module}/`} prefetch={false}>Source path: /analytics/m/{entry.module}/</Link>
            <details className="paper-fields">
              <summary>Evidence field inventory ({entry.fields.length} {entry.fields.length === 1 ? "path" : "paths"})</summary>
              <ul>
                {entry.fields.map(field => <li key={field} className="mono">{field}</li>)}
              </ul>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}

type ResultBlock = Extract<PaperBlock, { type: "p" | "callout" }>;

function mainResult(paper: Paper): ResultBlock | null {
  const callout = paper.sections.flatMap(section => section.blocks).find(block => block.type === "callout");
  if (callout) return callout;
  return paper.sections.find(section => section.id === "results")?.blocks.find(block => block.type === "p") || null;
}

function MobileResult({ paper }: { paper: Paper }) {
  const result = mainResult(paper);
  if (!result) return null;
  const label = result.type === "callout" ? result.label : "First published result";
  const text = result.text;
  return <aside className="paper-mobile-result" aria-label="Result and limit">
    <p className="overline">{label}</p>
    <p>{text}</p>
    <p className="paper-mobile-limit"><span>Limit</span> {paper.limitations[0]}</p>
  </aside>;
}

export function PaperArticle({ paper }: { paper: Paper }) {
  const related = resolveRelated(paper.related);
  const integrityNotices = noticesForPaper(paper.evidence);
  const evidenceModuleIds = paper.evidence.map(entry => entry.module);
  const hasLimitationsSection = paper.sections.some(section => section.id === "limitations");
  return (
    <article className="paper">
      <header className="paper-head">
        <p className="overline">Research paper</p>
        <h1 className="serif">{paper.title}</h1>
        <p className="paper-sub">{paper.subtitle}</p>
        <p className="mono paper-byline">
          {paper.authors.join(", ")} &middot; {paper.date} &middot; {SPORT_LABELS[paper.sport]} &middot; {readingMinutes(paper)} min read
        </p>
      </header>

      <MobileResult paper={paper} />

      <section className="paper-abstract" aria-labelledby="paper-abstract-heading">
        <h2 id="paper-abstract-heading" className="overline">Abstract</h2>
        <p>{paper.abstract}</p>
      </section>

      <DataIntegrityNotice notices={integrityNotices} moduleIds={evidenceModuleIds} />

      <nav className="paper-toc" aria-label="Sections">
        <p className="overline">Contents</p>
        <ol>
          {paper.sections.map((section, index) => (
            <li key={section.id}>
              <a href={`#${section.id}`}><span className="mono">{index + 1}</span> {section.heading}</a>
            </li>
          ))}
        </ol>
      </nav>

      {paper.sections.map((section, index) => (
        <section key={section.id} id={section.id} className="paper-section" aria-labelledby={`paper-section-${section.id}`}>
          <h2 id={`paper-section-${section.id}`}><span className="mono paper-number">{index + 1}</span> {section.heading}</h2>
          {section.blocks.map((block, position) => <PaperBlockView key={position} block={block} />)}
        </section>
      ))}

      <EvidenceBox paper={paper} />

      {!hasLimitationsSection ? <section className="paper-box" aria-labelledby="paper-limitations">
        <h2 id="paper-limitations">Limitations</h2>
        <ul className="paper-list">
          {paper.limitations.map((item, index) => <li key={index}>{item}</li>)}
        </ul>
      </section> : null}

      {related.length ? (
        <section className="paper-box" aria-labelledby="paper-related">
          <h2 id="paper-related">Related</h2>
          <ul className="paper-related">
            {related.map(link => (
              <li key={`${link.kind}-${link.id}`}>
                <Link href={link.href} prefetch={false}>{link.title}</Link>
                <span className="paper-note">{kindLabels[link.kind]}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}
