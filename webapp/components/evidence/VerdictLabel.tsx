// VerdictLabel.tsx -- a verdict is only ever one of the evidence packet's labels
// (docs/JOB_EVIDENCE_PACKET.md), rendered with the qualifier the packet attaches:
// MATCHES_CLOSE is always "underpowered" (the interval includes zero but cannot
// resolve a gap below its MDE), MODEL_SHARPER_PROVISIONAL always carries its
// small-sample qualifier. The prop type refuses any other string at compile time and
// the component throws at render time, so a page cannot invent a verdict. Server-safe.
import "./evidence.css";
import { fmtDecimal } from "./kit";

export const PACKET_VERDICTS = [
  "MATCHES_CLOSE",
  "TRAILS_CLOSE",
  "BEHIND",
  "INSUFFICIENT",
  "MODEL_SHARPER_PROVISIONAL",
] as const;

export type PacketVerdict = (typeof PACKET_VERDICTS)[number];

/** The qualifier the packet attaches to the label; rendered with it by default. */
export const VERDICT_QUALIFIER: Partial<Record<PacketVerdict, string>> = {
  MATCHES_CLOSE: "underpowered",
  MODEL_SHARPER_PROVISIONAL: "small-sample retrospective diagnostic; not evidence of market outperformance",
};

/** What each label licenses, in calibration language only (title text). */
export const VERDICT_MEANING: Record<PacketVerdict, string> = {
  MATCHES_CLOSE: "The 95% interval on the model-minus-close gap includes zero, and the sample cannot resolve a gap below its MDE: not resolved, not parity.",
  TRAILS_CLOSE: "The model scores worse than the devigged close and the 95% interval on the gap excludes zero.",
  BEHIND: "The model trails the market reference on this market; the gap is attributed to information the market prices and the model cannot see.",
  INSUFFICIENT: "Too few qualified games or weeks to score; no verdict is drawn.",
  MODEL_SHARPER_PROVISIONAL: "A small-sample retrospective diagnostic in which the model scored sharper than the market reference; provisional, not evidence of market outperformance.",
};

export function isPacketVerdict(value: unknown): value is PacketVerdict {
  return typeof value === "string" && (PACKET_VERDICTS as readonly string[]).includes(value);
}

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
