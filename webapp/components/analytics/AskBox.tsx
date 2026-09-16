"use client";
// Ask Scout is a client-side reader for committed, cited answers. It has no LLM,
// no fetch, and no live-data path; retrieval only selects an existing envelope.
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Receipt, type ReceiptData } from "./Receipt";
import Link from "next/link";

// Source JSON files are static assets, not routes: a plain anchor (base-path prefixed by hand)
// avoids the router prefetching them as RSC payloads (a 404 per click on the exported site).
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";
import type { Verdict } from "./VerdictDot";
import { typeset } from "@/lib/analytics/format";
import {
  resolveQuestion,
  type AskAnswer,
  type AskEntry,
  type ResolvedQuestion,
} from "@/lib/analytics/askSearch";

export type { AskEntry } from "@/lib/analytics/askSearch";

export interface AskTour {
  label: string;
  questions: string[];
}

const statusMap: Record<AskAnswer["status"], { verdict: Verdict; label: string }> = {
  ok: { verdict: "descriptive_only", label: "CITED" },
  no_data: { verdict: "not_testable", label: "NO_DATA" },
  refused: { verdict: "not_testable", label: "NOT ADVICE" },
};

function receiptFor(answer: AskAnswer): ReceiptData {
  const stamp = statusMap[answer.status] || statusMap.ok;
  return {
    sourceArtifact: answer.source_artifact,
    asOf: answer.as_of && answer.as_of !== "unknown" ? answer.as_of : undefined,
    verdict: stamp.verdict,
    label: stamp.label,
  };
}

const bar: CSSProperties = {
  display: "flex", alignItems: "center", gap: 10, background: "var(--paper-raised)",
  border: "1px solid var(--rule-strong)", borderRadius: "var(--radius-pill, 999px)",
  padding: "10px 10px 10px 18px", boxShadow: "var(--shadow-card)",
};
const inputStyle: CSSProperties = {
  border: 0, background: "transparent", flex: 1, minWidth: 0, fontFamily: "var(--font-sans)",
  fontSize: 16, color: "var(--ink)",
};
const submit: CSSProperties = {
  border: 0, background: "var(--accent)", color: "var(--accent-ink-on, #fff)",
  fontFamily: "var(--font-sans)", fontWeight: 600, fontSize: 15, padding: "10px 20px",
  minHeight: 44, borderRadius: "var(--radius-pill, 999px)", cursor: "pointer",
};
const pill: CSSProperties = {
  fontSize: 13, color: "var(--accent)", border: "1px solid var(--rule-strong)",
  borderRadius: "var(--radius-pill, 999px)", display: "inline-flex", alignItems: "center",
  minHeight: 44, padding: "6px 14px", background: "var(--paper-raised)", cursor: "pointer",
  fontFamily: "var(--font-sans)", textAlign: "left", lineHeight: 1.35,
};
const answerStyle: CSSProperties = { fontSize: 15.5, color: "var(--ink-2)", lineHeight: 1.6 };
const questionStyle: CSSProperties = { fontSize: 13, color: "var(--ink-3)", marginBottom: 6 };
const chipRow: CSSProperties = { display: "flex", flexWrap: "wrap", gap: "6px 16px", marginTop: 10 };

const PACK_LABELS: Record<string, string> = {
  calibration: "Calibration checkpoints",
  mlb_batters: "MLB batters",
  mlb_pitch: "MLB pitch types",
  nba_players: "NBA players",
  nba_teams: "NBA teams",
  soccer: "Soccer teams",
  tennis: "Tennis players",
};

function profilePath({ pack, slug }: { pack: string; slug: string }): string {
  return `/analytics/players/${pack}/${slug}`;
}

function AnswerEnvelope({ result, query, onAsk, excludedQuestions }: {
  result: ResolvedQuestion;
  query: string;
  onAsk: (question: string) => void;
  excludedQuestions: Set<string>;
}): ReactNode {
  if (result.kind === "none" || !result.entry) {
    const unavailable = result.kind === "unavailable";
    return (
      <section aria-label={unavailable ? "Scout corpus unavailable" : "No verified answer"} style={envelope(true)}>
        <Marker neutral />
        <div>
          <div style={questionStyle}>{query}</div>
          {result.compareOffer ? <div style={{ ...chipRow, margin: "0 0 10px" }}>
            <Link href={result.compareOffer.href} style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)" }}>{result.compareOffer.label}</Link>
          </div> : null}
          <div style={answerStyle}>
            {result.entityChoices?.length ? (
              <>
                <strong style={{ color: "var(--ink)" }}>Did you mean:</strong>
                <div style={chipRow}>
                  {result.entityChoices.map((entity) => (
                    <Link key={`${entity.pack}:${entity.slug}`} href={profilePath(entity)} style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)" }}>
                      {entity.name} ({PACK_LABELS[entity.pack] || entity.pack})
                    </Link>
                  ))}
                </div>
              </>
            ) : unavailable ? (
              <><strong style={{ color: "var(--ink)" }}>Scout's public corpus is unavailable.</strong> No answer can be verified until its committed sources load.</>
            ) : (
              <><strong style={{ color: "var(--ink)" }}>No verified result.</strong> Scout searches published questions and answers. Try a player, team, sport, or a metric such as calibration, Brier score, pitch mix, or home advantage.</>
            )}
          </div>
        </div>
      </section>
    );
  }

  const { entry } = result;
  const related = result.kind === "related";
  const neutral = related || entry.a.status !== "ok";
  const publicArtifact = /^webapp\/public\/data\/showcase\/[a-z0-9_]+\.json$/i.test(entry.a.source_artifact);
  const sourceHref = publicArtifact ? entry.a.source_artifact.slice("webapp/public".length) : "/data/ask/corpus.json";
  const explorePath = /^\/analytics\/(?:research\/[a-z0-9-]+\/|players\/[a-z0-9_]+\/[a-z0-9_]+|m\/[a-z0-9_]+)$/i.test(entry.a.explore_path || "") ? entry.a.explore_path : null;
  const destinationLabel = entry.bucket === "public-entity-profile" ? "Open profile" : entry.bucket === "public-analytics-module" ? "Open module" : "Read analysis";
  const followUps = result.followUps.filter(question => question !== query && !excludedQuestions.has(question));
  return (
    <section aria-label={related ? "Related cited answer" : "Cited answer"} style={envelope(neutral)}>
      <Marker neutral={neutral} />
      <div style={{ minWidth: 0 }}>
        <div style={questionStyle}>{query}</div>
        {related ? (
          <p style={{ ...answerStyle, margin: "0 0 10px" }}>
            <strong style={{ color: "var(--ink)" }}>Related cited note, not a direct answer.</strong>
            {" "}Closest available question:
          </p>
        ) : null}
        {related ? <div style={{ ...questionStyle, fontStyle: "italic" }}>{entry.q}</div> : null}
        <div style={answerStyle}>{typeset(entry.a.answer)}</div>
        <div style={chipRow}>
          {result.compareOffer ? <Link href={result.compareOffer.href} style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)" }}>{result.compareOffer.label}</Link> : null}
          {explorePath ? <Link href={explorePath} style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)" }}>{destinationLabel}</Link> : null}
          <Receipt {...receiptFor(entry.a)} />
          <a href={`${BASE_PATH}${sourceHref}`} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--accent)" }}>{publicArtifact ? "Open published source" : "Open published answer record"}</a>
        </div>
        {followUps.length > 0 ? (
          <div style={{ marginTop: 16 }}>
            <div className="overline" style={{ color: "var(--ink-3)", marginBottom: 7 }}>Continue exploring</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {followUps.map((question) => (
                <button key={question} type="button" style={pill} onClick={() => onAsk(question)}>{question}</button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function Marker({ neutral }: { neutral: boolean }) {
  return <span aria-hidden style={{ width: 26, height: 26, borderRadius: "50%", flex: "0 0 auto", opacity: 0.9, background: neutral ? "var(--null)" : "var(--signal)" }} />;
}

function envelope(neutral: boolean): CSSProperties {
  return {
    background: "var(--paper-tint)", borderLeft: `2px solid ${neutral ? "var(--null)" : "var(--accent)"}`,
    borderRadius: "var(--radius-card, 10px)", padding: "20px 22px", display: "flex", gap: 14,
  };
}

export function AskBox({ entries, tours }: { entries: AskEntry[]; tours: AskTour[] }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [result, setResult] = useState<ResolvedQuestion | null>(null);

  const updateUrl = (question: string) => {
    const url = new URL(window.location.href);
    if (question) url.searchParams.set("q", question);
    else url.searchParams.delete("q");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  };
  const run = (question: string) => {
    const next = question.trim();
    setQuery(question);
    setSubmittedQuery(next);
    setResult(next ? resolveQuestion(next, entries) : null);
    updateUrl(next);
  };
  const clear = () => {
    setQuery("");
    setSubmittedQuery("");
    setResult(null);
    updateUrl("");
  };
  const askFollowUp = (question: string) => {
    run(question);
    requestAnimationFrame(() => resultRef.current?.focus());
  };
  const askTourAndFocus = (question: string) => {
    run(question);
    requestAnimationFrame(() => inputRef.current?.focus());
  };
  const suggestedQuestions = new Set(tours.flatMap(tour => tour.questions));

  useEffect(() => {
    const prefilled = new URLSearchParams(window.location.search).get("q");
    if (prefilled) run(prefilled);
    // URL prefill is intentionally read once for static export.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <form role="search" style={bar} onSubmit={(event) => { event.preventDefault(); run(query); }}>
        <span aria-hidden style={{ width: 24, height: 24, borderRadius: "50%", background: "var(--signal)", flex: "0 0 auto", opacity: 0.9 }} />
        <input
          ref={inputRef}
          style={inputStyle}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") clear();
          }}
          placeholder="Ask about a player, team, sport, or metric..."
          aria-label="Ask Scout a question"
          aria-describedby="scout-help"
          enterKeyHint="search"
        />
        <button type="submit" style={submit} disabled={!query.trim()} aria-label="Search Scout's cited answers">Ask</button>
      </form>
      <p id="scout-help" style={{ margin: "8px 6px 0", fontSize: 12.5, color: "var(--ink-3)" }}>
        Press Enter to search. Escape clears the question. Scout searches published answers with source links.
      </p>

      <div ref={resultRef} tabIndex={-1} role="region" aria-label="Scout answer" aria-live="polite" aria-atomic="true" style={result ? { marginTop: 16 } : undefined}>
        {result ? <AnswerEnvelope result={result} query={submittedQuery} onAsk={askFollowUp} excludedQuestions={suggestedQuestions} /> : null}
      </div>

      <section aria-label="Suggested Scout questions" style={{ margin: "22px 0 10px" }}>
        {tours.map((tour) => (
          <div key={tour.label} style={{ marginBottom: 12 }}>
            <span className="overline" style={{ display: "block", marginBottom: 6, color: "var(--ink-3)" }}>{tour.label}</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {tour.questions.map((question) => (
                <button key={question} type="button" style={pill} onClick={() => askTourAndFocus(question)}>{question}</button>
              ))}
            </div>
          </div>
        ))}
      </section>
      <p style={{ fontSize: 13, color: "var(--ink-3)", margin: "8px 0 28px" }}>
        Scout searches published answers and links each result to its source.
      </p>
    </div>
  );
}

export default AskBox;
