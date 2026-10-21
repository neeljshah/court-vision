"use client";
// Ask Scout is a search over prepared answers. It is a client-side reader for
// committed, cited corpus entries: no LLM, no fetch, no live-data path. Retrieval
// only selects an existing entry (AskAnswerEnvelope) or says that none matches
// and offers the closest prepared questions (AskNoMatch).
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { AskAnswerEnvelope } from "./AskAnswerEnvelope";
import { AskNoMatch } from "./AskNoMatch";
import { pill } from "./askStyles";
import { resolveQuestion, type AskEntry, type ResolvedQuestion } from "@/lib/analytics/askSearch";

export type { AskEntry } from "@/lib/analytics/askSearch";

export interface AskTour {
  label: string;
  questions: string[];
}

export const LOADING_HELP = "Loading the prepared answers...";
export const READY_HELP = "Press Enter to search. Escape clears the question. Every result is a prepared answer shown verbatim with its source and as-of date; nothing is generated.";

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

export function AskBox({ entries, tours }: { entries: AskEntry[]; tours: AskTour[] }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [ready, setReady] = useState(false);
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
    setReady(true);
    // URL prefill is intentionally read once for static export.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const answered = result?.kind === "direct" && result.entry ? result.entry : null;

  return (
    <div>
      <form role="search" aria-busy={!ready} style={bar} onSubmit={(event) => { event.preventDefault(); if (ready) run(query); }}>
        <span aria-hidden style={{ width: 24, height: 24, borderRadius: "50%", background: "var(--signal)", flex: "0 0 auto", opacity: 0.9 }} />
        <input
          ref={inputRef}
          style={inputStyle}
          value={query}
          disabled={!ready}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") clear();
          }}
          placeholder="Search the prepared answers: a player, team, metric, or method..."
          aria-label="Ask Scout a question"
          aria-describedby="scout-help"
          enterKeyHint="search"
        />
        <button type="submit" style={submit} disabled={!ready || !query.trim()} aria-label="Search Scout's cited answers">Search</button>
      </form>
      <p id="scout-help" style={{ margin: "8px 6px 0", fontSize: 12.5, color: "var(--ink-3)" }}>
        {ready ? READY_HELP : LOADING_HELP}
      </p>

      <div ref={resultRef} tabIndex={-1} role="region" aria-label="Scout answer" aria-live="polite" aria-atomic="true" style={result ? { marginTop: 16 } : undefined}>
        {result && answered
          ? <AskAnswerEnvelope entry={answered} result={result} query={submittedQuery} onAsk={askFollowUp} excludedQuestions={suggestedQuestions} entries={entries} />
          : result ? <AskNoMatch result={result} query={submittedQuery} onAsk={askFollowUp} /> : null}
      </div>

      <section id="scout-suggestions" aria-label="Suggested Scout questions" style={{ margin: "22px 0 10px" }}>
        {tours.map((tour) => (
          <div key={tour.label} style={{ marginBottom: 12 }}>
            <span className="overline" style={{ display: "block", marginBottom: 6, color: "var(--ink-3)" }}>{tour.label}</span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {tour.questions.map((question) => (
                <button key={question} type="button" style={pill} disabled={!ready} onClick={() => askTourAndFocus(question)}>{question}</button>
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
