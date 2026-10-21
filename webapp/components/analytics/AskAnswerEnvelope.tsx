"use client";
// The cited-answer envelope: renders one prepared corpus entry verbatim with its
// receipt (source artifact, as-of), its published destination and follow-ups.
// Only a direct match reaches this component; see AskNoMatch for everything else.
import type { ReactNode } from "react";
import Link from "next/link";
import { Receipt, type ReceiptData } from "./Receipt";
import { DataIntegrityNotice } from "./DataIntegrityNotice";
import type { Verdict } from "./VerdictDot";
import { typeset } from "@/lib/analytics/format";
import { isReadingRoomPath } from "@/lib/analytics/scoutInspectorAnswers";
import { scoutIntegrity } from "@/lib/analytics/scoutIntegrity";
import type { AskAnswer, AskEntry, ResolvedQuestion } from "@/lib/analytics/askSearch";
import { answerStyle, chipLink, chipRow, envelope, markerStyle, pill, questionStyle } from "./askStyles";

// Source JSON files are static assets, not routes: a plain anchor (base-path prefixed by hand)
// avoids the router prefetching them as RSC payloads (a 404 per click on the exported site).
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

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

const DESTINATION_LABELS: Record<string, string> = {
  "public-entity-profile": "Open profile",
  "public-analytics-module": "Open module",
  "public-inspector": "Open inspector",
  "public-explainer": "Read explainer",
  "public-paper": "Read paper",
};

function explorePathFor(entry: AskEntry, entries: AskEntry[]): string | null {
  const path = entry.a.explore_path || "";
  const standardPath = /^\/analytics\/(?:research\/[a-z0-9-]+\/|players\/[a-z0-9_]+\/[a-z0-9_]+|m\/[a-z0-9_]+)$/i.test(path);
  const researchViewPath = /^\/analytics\/research\/[a-z0-9-]+\/\?(?:q|metric|row)=[^#\s&]*(?:&(?:q|metric|row)=[^#\s&]*)*$/i.test(path);
  return standardPath || researchViewPath || isReadingRoomPath(path, entries) ? path : null;
}

export function AskAnswerEnvelope({ entry, result, query, onAsk, excludedQuestions, entries }: {
  entry: AskEntry;
  result: ResolvedQuestion;
  query: string;
  onAsk: (question: string) => void;
  excludedQuestions: Set<string>;
  entries: AskEntry[];
}): ReactNode {
  const integrity = scoutIntegrity(entry.a);
  const neutral = entry.a.status !== "ok";
  const publicArtifact = /^webapp\/public\/data\/(?:showcase|papers|explainers)\/[a-z0-9_-]+\.json$/i.test(entry.a.source_artifact);
  const sourceHref = publicArtifact ? entry.a.source_artifact.slice("webapp/public".length) : "/data/ask/corpus.json";
  const explorePath = explorePathFor(entry, entries);
  const destinationLabel = DESTINATION_LABELS[entry.bucket] || "Read analysis";
  const followUps = result.followUps.filter(question => question !== query && !excludedQuestions.has(question));
  return (
    <section aria-label="Cited answer" style={envelope(neutral)}>
      <span aria-hidden style={markerStyle(neutral)} />
      <div style={{ minWidth: 0 }}>
        <div style={questionStyle}>{query}</div>
        {entry.q !== query ? <div style={{ ...questionStyle, fontStyle: "italic" }}>Prepared question: {entry.q}</div> : null}
        <DataIntegrityNotice notices={integrity.notices} moduleIds={integrity.moduleIds} />
        <div style={answerStyle}>{typeset(entry.a.answer)}</div>
        <div style={chipRow}>
          {result.compareOffer ? <Link href={result.compareOffer.href} style={chipLink}>{result.compareOffer.label}</Link> : null}
          {explorePath ? <Link href={explorePath} style={chipLink}>{destinationLabel}</Link> : null}
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
