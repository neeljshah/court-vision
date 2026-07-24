// HonestBanner.tsx -- the mandatory honesty banner atop atlas + descriptive
// artifacts and the methodology page. Thin, server-renderable, tokens only.
//
// Three kinds, color = meaning (DESIGN sec.3 vocabulary):
//   descriptive_only  -> info blue: measured summaries, not predictions/edge.
//   no_edge           -> info blue: we claim calibration, never a dollar edge.
//   validation_pending-> stale amber: artifact absent on this clone.
// Never green by default; the honest state is styled with the same care as a win.

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type HonestBannerKind =
  | "descriptive_only"
  | "no_edge"
  | "validation_pending";

const COPY: Record<HonestBannerKind, { word: string; body: string }> = {
  descriptive_only: {
    word: "descriptive only",
    body:
      "These are measured summaries of past data. They are not predictions and " +
      "not an edge claim.",
  },
  no_edge: {
    word: "no edge claimed",
    body:
      "This site reports calibration and sharpness only, never a dollar edge, " +
      "ROI, or bankroll result. An honest null is a success.",
  },
  validation_pending: {
    word: "validation pending",
    body:
      "The cited artifact was not built on this clone, so the number is not yet " +
      "measured here. Run the reproduce command to generate it.",
  },
};

const TONE: Record<HonestBannerKind, string> = {
  descriptive_only: "border-info/40 text-info",
  no_edge: "border-info/40 text-info",
  validation_pending: "border-stale/50 text-stale",
};

export function HonestBanner({
  kind,
  asOf,
  children,
}: {
  kind: HonestBannerKind;
  asOf?: string | null;
  children?: ReactNode;
}) {
  const { word, body } = COPY[kind];
  return (
    <div
      role="note"
      className={cn(
        "flex flex-col gap-1 border bg-card px-3 py-2 sm:flex-row sm:items-baseline sm:gap-3",
        TONE[kind]
      )}
    >
      <span className="microlabel shrink-0 tracking-wider">{word}</span>
      <p className="m-0 text-sm leading-relaxed text-muted-foreground">
        {children ?? body}
      </p>
      {asOf != null && (
        <span className="ml-auto shrink-0 font-data text-[11px] text-faint">
          as of {asOf}
        </span>
      )}
    </div>
  );
}
