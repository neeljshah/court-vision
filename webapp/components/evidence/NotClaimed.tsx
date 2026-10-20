// NotClaimed.tsx -- the standard "what this is not" block: paper only, no orders, no
// edge / ROI / profit claim, with the receipt back to the evidence packet, the single
// truth source. Mount it on the terminal pages (home, paper desk, paper trading); the
// analytics half keeps its own calibration-only copy rule and does not negate words it
// never uses. Server-safe.
import { useId } from "react";
import "./evidence.css";
import { FIGURES_AS_OF } from "@/lib/figures";
import { ReceiptChip } from "./ReceiptChip";
import { PACKET_PATH } from "./kit";

export const NOT_CLAIMED_LINES = [
  "Paper only. No real-money order has been placed; real money stays human-gated behind a forward closing-line-value record.",
  "No edge, ROI or profit claim. Every figure is a calibration or execution-quality measurement against the devigged close, not a track record.",
  "Retracted headline figures are listed in the evidence packet with their corrections and are never quoted as current.",
] as const;

export interface NotClaimedProps {
  /** One extra sentence specific to the page, rendered after the standard lines. */
  children?: React.ReactNode;
  className?: string;
}

export function NotClaimed({ children, className }: NotClaimedProps) {
  const titleId = useId();
  return (
    <aside className={["ev-notclaimed", className ?? ""].filter(Boolean).join(" ")} aria-labelledby={titleId}>
      <p className="ev-notclaimed__title" id={titleId}>What this is not</p>
      <ul>
        {NOT_CLAIMED_LINES.map((line) => <li key={line}>{line}</li>)}
      </ul>
      {children ? <p className="ev-notclaimed__extra">{children}</p> : null}
      <p className="ev-notclaimed__foot">
        <span>truth source</span>
        <ReceiptChip source={PACKET_PATH} asOf={FIGURES_AS_OF} status="descriptive_only" />
      </p>
    </aside>
  );
}

export default NotClaimed;
