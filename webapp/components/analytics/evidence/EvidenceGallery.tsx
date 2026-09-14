"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Search, X } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type { EvidenceChart } from "@/lib/analytics/evidenceHub";

export interface EvidenceGalleryProps {
  readonly charts: EvidenceChart[];
}

function statusLabel(status: EvidenceChart["status"]): string {
  return status === "partial" ? "Partial documentation" : "Published";
}

function asOfLabel(asOf: string | null): string {
  if (!asOf) return "As-of not stamped";
  const dated = /^\d{4}-\d{2}-\d{2}(?:$|[T\s])/.test(asOf);
  return `As of ${dated ? asOf.slice(0, 10) : asOf}`;
}

function normalizeSearch(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

interface ChartDialogProps {
  readonly chart: EvidenceChart;
}

function ChartDialog({ chart }: ChartDialogProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>
        <button ref={triggerRef} className="evidence-preview" type="button" aria-label={`Open larger view of ${chart.title}`}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={chart.imageSrc} alt="" loading="lazy" />
          <span>View chart</span>
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="evidence-dialog-overlay" />
        <Dialog.Content className="cv-workspace evidence-dialog" aria-describedby={`chart-description-${chart.id}`} onCloseAutoFocus={(event) => {
          event.preventDefault();
          triggerRef.current?.focus();
        }}>
          <div className="evidence-dialog-head">
            <div><Dialog.Title>{chart.title}</Dialog.Title><p id={`chart-description-${chart.id}`}>{asOfLabel(chart.asOf)}</p></div>
            <Dialog.Close className="evidence-dialog-close" aria-label="Close chart"><X size={19} /></Dialog.Close>
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={chart.imageSrc} alt={`${chart.title} chart`} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function EvidenceGallery({ charts }: EvidenceGalleryProps) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | EvidenceChart["status"]>("all");
  const results = useMemo(() => charts.filter((chart) => {
    const terms = normalizeSearch(`${chart.title} ${chart.description} ${chart.id}`);
    return (status === "all" || chart.status === status) && terms.includes(normalizeSearch(query));
  }), [charts, query, status]);

  return <section className="evidence-gallery-section" aria-labelledby="evidence-gallery-title">
    <div className="evidence-section-heading"><div><p className="cv-eyebrow"><span className="cv-square" />Evidence gallery</p><h2 id="evidence-gallery-title">Published charts, linked to their source</h2></div><p>Static artifacts from the public manifest. This page does not report a live backend state.</p></div>
    <div className="evidence-controls">
      <label className="evidence-search"><Search size={17} aria-hidden="true" /><span className="sr-only">Search published charts</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search charts and methods" /></label>
      <label className="evidence-status">Documentation status<select value={status} onChange={(event) => setStatus(event.target.value as "all" | EvidenceChart["status"])}><option value="all">All charts</option><option value="published">Published</option><option value="partial">Partial documentation</option></select></label>
    </div>
    <p className="evidence-result-count" role="status">{results.length} published chart{results.length === 1 ? "" : "s"} shown</p>
    {results.length ? <div className="evidence-grid">{results.map((chart) => <article className="evidence-card" key={chart.id}>
      <ChartDialog chart={chart} />
      <div className="evidence-card-body"><div className="evidence-card-top"><span className={`evidence-status-chip ${chart.status}`}>{statusLabel(chart.status)}</span><span>{asOfLabel(chart.asOf)}</span></div><h3>{chart.title}</h3><p>{chart.description}</p><div className="evidence-links"><a href={chart.sourceUrl} target="_blank" rel="noreferrer">Source module</a>{chart.evidenceUrl ? <a href={chart.evidenceUrl} target="_blank" rel="noreferrer">Evidence note</a> : null}</div></div>
    </article>)}</div> : <p className="evidence-empty">No published charts match that search. Try a different term or clear the status filter.</p>}
  </section>;
}
