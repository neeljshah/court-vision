"use client";
// The no-answer envelope. Scout has no prepared answer for the question, so it
// says so plainly and offers the closest prepared questions as buttons. It never
// shows the nearest paragraph as if it answered the query.
import type { ReactNode } from "react";
import Link from "next/link";
import type { ResolvedQuestion } from "@/lib/analytics/askSearch";
import { answerStyle, chipLink, chipRow, envelope, markerStyle, PACK_LABELS, pill, profilePath, questionStyle, strong } from "./askStyles";

export const NO_MATCH_LABEL = "No prepared answer";

function Body({ result, onAsk }: { result: ResolvedQuestion; onAsk: (question: string) => void }): ReactNode {
  if (result.entityChoices?.length) {
    return (
      <>
        <strong style={strong}>Did you mean:</strong>
        <div style={chipRow}>
          {result.entityChoices.map((entity) => (
            <Link key={`${entity.pack}:${entity.slug}`} href={profilePath(entity)} style={chipLink}>
              {entity.name} ({PACK_LABELS[entity.pack] || entity.pack})
            </Link>
          ))}
        </div>
      </>
    );
  }
  if (result.kind === "unavailable") {
    return <><strong style={strong}>Scout&apos;s prepared answers are unavailable.</strong> Nothing can be shown until the committed corpus loads.</>;
  }
  const closest = result.closest;
  return (
    <>
      <strong style={strong}>No prepared answer for this question.</strong>{" "}
      {closest.length > 0
        ? <>Here {closest.length === 1 ? "is the closest prepared topic" : `are the ${closest.length === 3 ? "three" : closest.length} closest prepared topics`}; open one to read its answer verbatim with its source:</>
        : <>No prepared topic shares a term with it.</>}
      {closest.length > 0 ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
          {closest.map((question) => (
            <button key={question} type="button" style={pill} onClick={() => onAsk(question)}>{question}</button>
          ))}
        </div>
      ) : null}
      <div style={{ marginTop: 10 }}>
        Scout is a search over prepared answers, not a model.{" "}
        <a href="#scout-suggestions" style={{ color: "var(--accent)", fontWeight: 700 }}>Explore published questions</a>.
      </div>
    </>
  );
}

export function AskNoMatch({ result, query, onAsk }: {
  result: ResolvedQuestion;
  query: string;
  onAsk: (question: string) => void;
}): ReactNode {
  const unavailable = result.kind === "unavailable";
  return (
    <section aria-label={unavailable ? "Scout corpus unavailable" : NO_MATCH_LABEL} style={envelope(true)}>
      <span aria-hidden style={markerStyle(true)} />
      <div style={{ minWidth: 0 }}>
        <div style={questionStyle}>{query}</div>
        {result.compareOffer ? <div style={{ ...chipRow, margin: "0 0 10px" }}>
          <Link href={result.compareOffer.href} style={chipLink}>{result.compareOffer.label}</Link>
        </div> : null}
        <div style={answerStyle}><Body result={result} onAsk={onAsk} /></div>
      </div>
    </section>
  );
}
