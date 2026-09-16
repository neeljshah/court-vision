"use client";
import { useState } from "react";
import Link from "next/link";
import {
  excerpt, filterPapers, paperHref, paperKeywords, paperSports, readingMinutes, SPORT_LABELS, type Paper,
} from "@/lib/analytics/papers";

export default function PapersIndex({ papers }: { papers: Paper[] }) {
  const [sport, setSport] = useState("any");
  const [keyword, setKeyword] = useState("any");
  const sports = paperSports(papers);
  const keywords = paperKeywords(papers);
  const visible = filterPapers(papers, sport, keyword);

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
              <button type="button" aria-pressed={sport === "any"} onClick={() => setSport("any")}>All sports</button>
              {sports.map(item => (
                <button key={item} type="button" aria-pressed={sport === item} onClick={() => setSport(item)}>
                  {SPORT_LABELS[item]}
                </button>
              ))}
            </div>
            <div className="paper-chips" role="group" aria-label="Filter by keyword">
              <button type="button" aria-pressed={keyword === "any"} onClick={() => setKeyword("any")}>All keywords</button>
              {keywords.map(item => (
                <button key={item} type="button" aria-pressed={keyword === item} onClick={() => setKeyword(item)}>{item}</button>
              ))}
            </div>
          </div>

          <p className="mono paper-count" role="status">
            {visible.length} of {papers.length} {papers.length === 1 ? "paper" : "papers"}
          </p>

          {visible.length === 0 ? (
            <p className="paper-empty">
              No paper matches these filters.
              <button type="button" onClick={() => { setSport("any"); setKeyword("any"); }}>Reset filters</button>
            </p>
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
