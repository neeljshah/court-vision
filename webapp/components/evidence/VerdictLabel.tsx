// VerdictLabel.tsx -- a verdict is only ever one of the evidence packet's labels
// (docs/JOB_EVIDENCE_PACKET.md), rendered with the qualifier the packet attaches:
// MATCHES_CLOSE is always "underpowered" (the interval includes zero but cannot
// resolve a gap below its MDE), MODEL_SHARPER_PROVISIONAL always carries its
// small-sample qualifier. The 17 labels, meanings and qualifiers live in
// lib/packetVerdicts.ts. The prop type refuses any other string at compile time and
// the component throws at render time, so a page cannot invent a verdict. Server-safe.
import "./evidence.css";
import { fmtDecimal } from "./kit";
import { PACKET_VERDICTS, VERDICT_MEANING, VERDICT_QUALIFIER, isPacketVerdict, type PacketVerdict } from "@/lib/packetVerdicts";

export { PACKET_VERDICTS, VERDICT_MEANING, VERDICT_QUALIFIER, isPacketVerdict } from "@/lib/packetVerdicts";
export type { PacketVerdict } from "@/lib/packetVerdicts";

/** A runtime string (from an artifact) narrowed to the packet set, or null when it is not one. */
export function toPacketVerdict(value: unknown): PacketVerdict | null {
  return isPacketVerdict(value) ? value : null;
}

export interface VerdictLabelProps {
  verdict: PacketVerdict;
  /** Minimum detectable effect, appended to the MATCHES_CLOSE qualifier when known. */
  mde?: number | null;
  /** Set false to render the bare label (the qualifier stays in the title). */
  qualifier?: boolean;
  className?: string;
}

export function verdictQualifier(verdict: PacketVerdict, mde?: number | null): string | null {
  const base = VERDICT_QUALIFIER[verdict] ?? null;
  if (verdict === "MATCHES_CLOSE" && typeof mde === "number") return `${base}, MDE ${fmtDecimal(mde)}`;
  return base;
}

export function VerdictLabel({ verdict, mde, qualifier = true, className }: VerdictLabelProps) {
  if (!isPacketVerdict(verdict)) {
    throw new Error(`VerdictLabel: "${String(verdict)}" is not a packet verdict; use one of ${PACKET_VERDICTS.join(", ")}`);
  }
  const q = verdictQualifier(verdict, mde);
  const title = `${verdict}${q ? ` (${q})` : ""}: ${VERDICT_MEANING[verdict]}`;
  return (
    <span className={["ev-verdict", className ?? ""].filter(Boolean).join(" ")} data-verdict={verdict} title={title}>
      <span className="ev-verdict__label">{verdict}</span>
      {qualifier && q ? <span className="ev-verdict__q">{q}</span> : null}
    </span>
  );
}

export default VerdictLabel;
