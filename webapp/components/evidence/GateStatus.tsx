// GateStatus.tsx -- the eval-gate ledger's status tokens (SHIP, SHIP_REVIEW, WORSE, ...),
// rendered in their own style with a plain-words gloss. They are a DIFFERENT vocabulary from
// the evidence packet's verdicts (lib/packetVerdicts.ts, rendered by VerdictLabel): a gate
// status is what one eval-gate run concluded about a candidate signal, never what the packet
// concluded about the model, and a SHIP is a calibration survivor, not anything shipped or an
// edge. Every render carries its gloss and the "gate ledger status, not a packet verdict" note;
// GateStatusLegend is the one-line legend a page shows once. None of these tokens may be added
// to packetVerdicts.ts (GateStatus.test.tsx checks). Server-safe: no hooks, no node:fs.
import "./evidence.css";
import { isPacketVerdict } from "@/lib/packetVerdicts";

export const GATE_STATUSES = [
  "SHIP", "SHIP_REVIEW", "WORSE", "STANDING_BASELINE_SET", "NULL_UNDERPOWERED",
  "VALIDATION_PENDING", "ALREADY_DONE_ON_CORE_METHOD", "COVERAGE_LOW", "DESCRIPTIVE_ONLY",
] as const;

export type GateStatusToken = (typeof GATE_STATUSES)[number];

/** Plain words for each token; the gloss is rendered with the token and in the legend. */
export const GATE_GLOSS: Record<GateStatusToken, string> = {
  SHIP: "passed every gate",
  SHIP_REVIEW: "passed, awaiting human review",
  WORSE: "worse than baseline",
  STANDING_BASELINE_SET: "baseline recorded",
  NULL_UNDERPOWERED: "null at this sample size",
  VALIDATION_PENDING: "not yet validated",
  ALREADY_DONE_ON_CORE_METHOD: "duplicate of the core method",
  COVERAGE_LOW: "too little coverage",
  DESCRIPTIVE_ONLY: "descriptive exhibit",
};

export const GATE_LEDGER_NOTE = "gate ledger status, not a packet verdict";

export const isGateStatus = (v: unknown): v is GateStatusToken =>
  typeof v === "string" && (GATE_STATUSES as readonly string[]).includes(v) && !isPacketVerdict(v);

/** A runtime string (from an artifact) narrowed to the gate set, or null when it is not one. */
export const toGateStatus = (v: unknown): GateStatusToken | null => (isGateStatus(v) ? v : null);

/** The gate tokens among some runtime strings, once each, in ledger order (for a page's legend). */
export function gateStatusesIn(values: Iterable<unknown>): GateStatusToken[] {
  const present = new Set<GateStatusToken>();
  for (const v of values) if (isGateStatus(v)) present.add(v);
  return GATE_STATUSES.filter((t) => present.has(t));
}

export function gateStatusTitle(token: GateStatusToken): string {
  return `${token}: ${GATE_GLOSS[token]}. ${GATE_LEDGER_NOTE}.`;
}

export interface GateStatusProps {
  token: GateStatusToken;
  /** Set false to keep the gloss in the title only (a legend on the page still prints it). */
  gloss?: boolean;
  className?: string;
}

export function GateStatus({ token, gloss = true, className }: GateStatusProps) {
  if (!isGateStatus(token)) {
    throw new Error(`GateStatus: "${String(token)}" is not a gate ledger status; use one of ${GATE_STATUSES.join(", ")}`);
  }
  return (
    <span className={["ev-gate", className ?? ""].filter(Boolean).join(" ")} data-gate={token} title={gateStatusTitle(token)}>
      <span className="ev-gate__kind">gate</span>
      <span className="ev-gate__label">{token}</span>
      {gloss ? <span className="ev-gate__gloss">{GATE_GLOSS[token]}</span> : null}
    </span>
  );
}

/** One line: the lead, then "TOKEN = gloss" for the tokens given (default: all), in ledger order. */
export function GateStatusLegend({ tokens = GATE_STATUSES, className }: {
  tokens?: readonly GateStatusToken[]; className?: string;
}) {
  const list = gateStatusesIn(tokens);
  if (list.length === 0) return null;
  return (
    <p className={["ev-gate-legend", className ?? ""].filter(Boolean).join(" ")} data-testid="gate-status-legend">
      <span className="ev-gate-legend__lead">Gate ledger statuses, not packet verdicts:</span>{" "}
      {list.map((t, i) => (
        <span key={t}>
          <span className="ev-gate-legend__token">{t}</span> = {GATE_GLOSS[t]}{i < list.length - 1 ? "; " : "."}
        </span>
      ))}
    </p>
  );
}

export default GateStatus;
