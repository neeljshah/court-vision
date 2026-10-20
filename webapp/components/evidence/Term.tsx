// Term.tsx -- a glossary tooltip for a technical term (Brier, devigged close, CRPS,
// Diebold-Mariano, MDE, calibration vs resolution). The trigger is a text-styled button
// (focusable, cursor: help) described by a tooltip that evidence.css reveals on hover or
// focus; the definition text is copied verbatim from docs/GLOSSARY.md (glossary.ts) and
// also sits in the title. Server-safe (useId only).
import { useId, type ReactNode } from "react";
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
  return (
    <span className={["ev-term", className ?? ""].filter(Boolean).join(" ")}>
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
