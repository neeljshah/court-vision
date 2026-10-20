// Term.tsx -- a glossary tooltip for a technical term (Brier, devigged close, CRPS,
// Diebold-Mariano, MDE, calibration vs resolution). The trigger is a text-styled button
// (focusable, cursor: help) described by a tooltip that evidence.css reveals on hover or
// focus; the definition text is copied verbatim from docs/GLOSSARY.md (glossary.ts) and
// also sits in the title. Escape hides an open tooltip (WCAG 1.4.13) until the pointer or
// focus re-enters, so this is a client component.
"use client";
import { useEffect, useId, useState, type ReactNode } from "react";
import "./evidence.css";
import { GLOSSARY, type GlossaryId } from "./glossary";

export interface TermProps {
  id: GlossaryId;
  /** The visible wording; defaults to the glossary term itself. */
  children?: ReactNode;
  className?: string;
}

export function Term({ id, children, className }: TermProps) {
  const entry = GLOSSARY[id];
  const tipId = useId();
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setDismissed(true); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  const reopen = () => setDismissed(false);
  return (
    <span className={["ev-term", className ?? ""].filter(Boolean).join(" ")}
      data-dismissed={dismissed || undefined} onMouseEnter={reopen} onFocus={reopen}>
      <button type="button" className="ev-term__word" aria-describedby={tipId} title={`${entry.term}: ${entry.text}`}>
        {children ?? entry.term}
      </button>
      <span role="tooltip" id={tipId} className="ev-term__tip">
        <b>{entry.term}</b> {entry.text}
      </span>
    </span>
  );
}

export default Term;
