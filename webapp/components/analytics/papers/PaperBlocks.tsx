// Block renderers for a research paper. Server-rendered, tokens only, ASCII only.
// A figure block reuses the shared editorial Figure frame when the source module
// publishes a chart, and falls back to a link card into the module page when it does not.
import Link from "next/link";
import { Figure } from "@/components/analytics/charts/Figure";
import { paperFigure } from "@/lib/analytics/papers.server";
import { getPublishedChartPresentation } from "@/lib/analytics/publishedChartPresentation";
import type { PaperBlock } from "@/lib/analytics/papers";

function isNumericCell(cell: string): boolean {
  return /^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:%|x)?$/.test(cell.trim());
}

function TableBlock({ block }: { block: Extract<PaperBlock, { type: "table" }> }) {
  return (
    <figure className="paper-table">
      <figcaption className="paper-caption">{block.caption}</figcaption>
      <p className="paper-scroll-hint" aria-hidden="true">Scroll horizontally to see all columns.</p>
      <div className="paper-scroll" role="region" tabIndex={0} aria-label={`${block.caption}, scroll horizontally for all columns`}>
        <table>
          <thead>
            <tr>{block.columns.map(column => <th key={column} scope="col">{column}</th>)}</tr>
          </thead>
          <tbody>
            {block.rows.map((row, index) => (
              <tr key={index}>
                {row.map((cell, position) => {
                  const cellClass = isNumericCell(cell) ? "paper-cell-numeric" : "paper-cell-prose";
                  return position === 0
                    ? <th key={position} scope="row" className={cellClass}>{cell}</th>
                    : <td key={position} className={cellClass}>{cell}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {block.note ? <p className="paper-note">{block.note}</p> : null}
    </figure>
  );
}

function FigureBlock({ block }: { block: Extract<PaperBlock, { type: "figure" }> }) {
  const published = paperFigure(block.module);
  const presentation = getPublishedChartPresentation(block.module);
  if (published?.chartSrc && presentation.approved) {
    return (
      <div className="paper-figure">
        <Figure source={published.source} asOf={published.asOf} title={published.title} verdict="descriptive_only">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={published.chartSrc} alt={`${published.title} chart`} style={{ width: "100%", height: "auto", display: "block" }} />
        </Figure>
        <p className="paper-caption">{block.caption}</p>
      </div>
    );
  }
  if (published?.chartSrc) {
    return (
      <div className="paper-figure">
        <Figure source={published.source} asOf={published.asOf} title={published.title} note={presentation.reason} verdict="descriptive_only">
          <div data-testid="published-data-figure" style={{ border: "1px solid var(--rule)", borderRadius: "var(--radius-card)", background: "var(--paper-tint)", padding: 12 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--font-mono)", fontSize: 12 }}>
              <thead><tr>{published.fallback.headers.map(header => <th key={header} style={{ color: "var(--ink-3)", textAlign: "left", padding: "6px 4px" }}>{header.replaceAll("_", " ")}</th>)}</tr></thead>
              <tbody>{published.fallback.rows.map((row, index) => <tr key={index}>{published.fallback.headers.map(header => <td key={header} style={{ borderTop: "1px solid var(--rule)", padding: "6px 4px" }}>{String(row[header] ?? "-")}</td>)}</tr>)}</tbody>
            </table>
          </div>
        </Figure>
        <p className="paper-caption">{block.caption}</p>
      </div>
    );
  }
  return (
    <Link href={`/analytics/m/${block.module}/`} className="paper-figure-card" prefetch={false}>
      <span className="overline">Source module</span>
      <strong>{published?.title || block.module.replace(/_/g, " ")}</strong>
      <span className="paper-caption">{block.caption}</span>
      <span className="paper-figure-hint">No chart is published for this source. Open the module page for its table of measurements.</span>
    </Link>
  );
}

export function PaperBlockView({ block }: { block: PaperBlock }) {
  if (block.type === "p") return <p className="paper-p">{block.text}</p>;
  if (block.type === "list") {
    return <ul className="paper-list">{block.items.map((item, index) => <li key={index}>{item}</li>)}</ul>;
  }
  if (block.type === "table") return <TableBlock block={block} />;
  if (block.type === "figure") return <FigureBlock block={block} />;
  if (block.type === "callout") {
    return (
      <aside className="paper-callout">
        <p className="overline">{block.label}</p>
        <p>{block.text}</p>
      </aside>
    );
  }
  return <p className="paper-math mono">{block.text}</p>;
}
