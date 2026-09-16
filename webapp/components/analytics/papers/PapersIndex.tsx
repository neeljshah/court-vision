"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  excerpt, filterPapers, paperHref, paperKeywords, paperSports, readingMinutes, SPORT_LABELS, type Paper,
} from "@/lib/analytics/papers";
import { paperViewSearch, readPaperViewState, type PaperViewState } from "@/lib/analytics/paperViewState";

export default function PapersIndex({ papers }: { papers: Paper[] }) {
  const [viewState, setViewState] = useState<PaperViewState>({ sport: "any", keyword: "any" });
  const sports = paperSports(papers);
  const keywords = paperKeywords(papers);
  const visible = filterPapers(papers, viewState.sport, viewState.keyword);
  const update = (change: Partial<PaperViewState>) => {
    const next = { ...viewState, ...change };
    setViewState(next);
    const url = new URL(window.location.href);
    url.search = paperViewSearch(url.search, next);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  };

  useEffect(() => {
    const restore = () => setViewState(readPaperViewState(window.location.search, papers));
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [papers]);

  return (
    <div className="wrap paper-index">
      <header className="paper-index-head">
        <p className="overline">Research papers</p>
        <h1 className="serif">Method notes with their receipts attached</h1>
        <p className="paper-sub">
          Each paper states a question, names the committed artifact behind every number, and ends on
          what the measurement does not establish. Calibration and description only.
        </p>
      </header>

      {papers.length === 0 ? (
        <p className="paper-empty">No papers are published yet. Each one appears here once its JSON passes the paper contract.</p>
      ) : (
        <>
          <div className="paper-filters">
            <div className="paper-chips" role="group" aria-label="Filter by sport">
              <button type="button" aria-pressed={viewState.sport === "any"} onClick={() => update({ sport: "any" })}>All sports</button>
              {sports.map(item => (
                <button key={item} type="button" aria-pressed={viewState.sport === item} onClick={() => update({ sport: item })}>
                  {SPORT_LABELS[item]}
                </button>
              ))}
            </div>
            <div className="paper-filter-controls">
              <label className="paper-keyword">
                <span>Keyword</span>
                <select value={viewState.keyword} onChange={event => update({ keyword: event.target.value })}>
                  <option value="any">All keywords</option>
                  {keywords.map(item => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <button className="paper-reset" type="button" onClick={() => update({ sport: "any", keyword: "any" })}>Reset filters</button>
            </div>
          </div>

          <p className="mono paper-count" role="status">
            {visible.length} of {papers.length} {papers.length === 1 ? "paper" : "papers"}
          </p>

          {visible.length === 0 ? (
            <p className="paper-empty">No paper matches these filters.</p>
          ) : (
            <div className="paper-cards">
              {visible.map(paper => (
                <Link key={paper.slug} href={paperHref(paper.slug)} className="paper-card" prefetch={false}>
                  <span className="mono paper-card-meta">
                    {paper.date} &middot; {SPORT_LABELS[paper.sport]} &middot; {readingMinutes(paper)} min &middot;{" "}
                    {paper.evidence.length} {paper.evidence.length === 1 ? "artifact" : "artifacts"}
                  </span>
                  <h2 className="serif">{paper.title}</h2>
                  <p className="paper-card-sub">{paper.subtitle}</p>
                  <p className="paper-card-abstract">{excerpt(paper.abstract)}</p>
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
