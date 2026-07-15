"use client";

// SignalVerdictBadge.tsx -- the leak-free gate verdict for a signal as a chip.
//
// Renders one of SHIP / REJECT / INSUFFICIENT_DATA / TIER3_BLOCKED with the
// deciding stat on hover. A SHIP chip ALWAYS carries the honest framing
// "calibration-only, vs_close UNPROVEN" -- a SHIP is a calibration survivor,
// never a profit/market edge. A REJECT is recorded as a SUCCESS, not a failure.
//
// NO $ field; no edge implied. Accessible: the chip has a title + an InfoTip and
// the verdict word is real text (not color-only).

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { InfoTip } from "./InfoTip";

export type SignalVerdict =
  | "SHIP"
  | "REJECT"
  | "INSUFFICIENT_DATA"
  | "TIER3_BLOCKED";

export interface SignalVerdictBadgeProps {
  verdict: SignalVerdict;
  /** The deciding stat / reason shown on hover (e.g. "clustered-DM p ~= 0.0015"). */
  stat?: string;
  className?: string;
}

const VERDICT_STYLE: Record<SignalVerdict, string> = {
  SHIP: "border-success text-success",
  REJECT: "border-border text-faint",
  INSUFFICIENT_DATA: "border-warning text-warning",
  TIER3_BLOCKED: "border-warning text-warning",
};

const VERDICT_LABEL: Record<SignalVerdict, string> = {
  SHIP: "SHIP",
  REJECT: "REJECT",
  INSUFFICIENT_DATA: "INSUFFICIENT DATA",
  TIER3_BLOCKED: "TIER-3 BLOCKED",
};

// The honest framing carried alongside each verdict. SHIP is NEVER an edge.
const VERDICT_NOTE: Record<SignalVerdict, string> = {
  SHIP: "calibration-only, vs_close UNPROVEN",
  REJECT: "recorded reject -- a success, not a failure",
  INSUFFICIENT_DATA: "not enough data to decide -- honest empty, no verdict",
  TIER3_BLOCKED: "blocked at tier-3 gate -- not promoted",
};

/** A gate-verdict chip with the deciding stat + honest framing on hover. */
export function SignalVerdictBadge({
  verdict,
  stat,
  className,
}: SignalVerdictBadgeProps) {
  const note = VERDICT_NOTE[verdict];
  const hover = stat ? `${stat} -- ${note}` : note;
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      <Badge
        variant="outline"
        title={hover}
        className={cn(
          "rounded-none font-data text-[10px] font-semibold uppercase tracking-wide",
          VERDICT_STYLE[verdict]
        )}
      >
        {VERDICT_LABEL[verdict]}
      </Badge>
      {verdict === "SHIP" && (
        <span className="font-data text-[10px] text-faint">
          {VERDICT_NOTE.SHIP}
        </span>
      )}
      <InfoTip text={hover} ariaLabel="what does this verdict mean?" />
    </span>
  );
}
