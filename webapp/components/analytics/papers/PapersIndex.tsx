"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  excerpt, filterPapers, paperHref, paperKeywords, paperSports, readingMinutes, SPORT_LABELS, type Paper,
} from "@/lib/analytics/papers";
import { paperViewSearch, readPaperViewState, type PaperViewState } from "@/lib/analytics/paperViewState";

const START_HERE_SLUGS = [
  "how-to-read-a-courtvision-paper",
  "calibration-reliability-by-sport-and-state",
  "how-proposed-signals-survive-testing",
];

export default function PapersIndex({ papers }: { papers: Paper[] }) {
  const [viewState, setViewState] = useState<PaperViewState>({ sport: "any", keyword: "any" });
  const [ready, setReady] = useState(false);
  const sports = paperSports(papers);
  const keywords = paperKeywords(papers);
  const visible = filterPapers(papers, viewState.sport, viewState.keyword);
  const startHere = START_HERE_SLUGS.flatMap(slug => {
    const paper = papers.find(entry => entry.slug === slug);
    return paper ? [paper] : [];
  });
  const update = (change: Partial<PaperViewState>) => {
    if (!ready) return;
    const next = { ...viewState, ...change };
    setViewState(next);
    const url = new URL(window.location.href);
    url.search = paperViewSearch(url.search, next);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  };

  useEffect(() => {
    const restore = () => {
      setViewState(readPaperViewState(window.location.search, papers));
      setReady(true);
    };
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
          <section className="paper-start" aria-labelledby="paper-start-heading">
            <div>
              <p className="overline">Start here</p>
              <h2 id="paper-start-heading" className="serif">A short route through the research record</h2>
              <p>Read the paper format first, then the calibration record, then the testing record.</p>
            </div>
            <ol>
              {startHere.map(paper => (
                <li key={paper.slug}>
                  <Link href={paperHref(paper.slug)} prefetch={false}>{paper.title}</Link>
                  <span>{paper.subtitle}</span>
                </li>
              ))}
            </ol>
          </section>
          <div className="paper-filters">
            <div className="paper-chips" role="group" aria-label="Filter by sport">
              <button type="button" disabled={!ready} aria-pressed={viewState.sport === "any"} onClick={() => update({ sport: "any" })}>All sports</button>
              {sports.map(item => (
                <button key={item} type="button" disabled={!ready} aria-pressed={viewState.sport === item} onClick={() => update({ sport: item })}>
                  {SPORT_LABELS[item]}
                </button>
              ))}
            </div>
            <div className="paper-filter-controls">
              <label className="paper-keyword">
                <span>Keyword</span>
                <select disabled={!ready} value={viewState.keyword} onChange={event => update({ keyword: event.target.value })}>
                  <option value="any">All keywords</option>
                  {keywords.map(item => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <button className="paper-reset" type="button" disabled={!ready} onClick={() => update({ sport: "any", keyword: "any" })}>Reset filters</button>
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
