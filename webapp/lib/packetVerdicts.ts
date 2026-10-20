// packetVerdicts.ts -- the verdict vocabulary of docs/JOB_EVIDENCE_PACKET.md
// (DESIGN_PRINCIPLES section 3). Nothing else may appear in a verdict slot.
export const PACKET_VERDICTS = [
  "TRAILS_CLOSE", "MATCHES_CLOSE", "UNDERPOWERED", "INSUFFICIENT", "PROVISIONAL",
  "CONFIRMED_LOCAL", "NULL", "NOT_TESTABLE", "REJECT", "FAILED_REPLICATION",
  "REPLICATED", "RETRACTED", "SUPERSEDED", "CORRECTED",
] as const;

export type PacketVerdict = (typeof PACKET_VERDICTS)[number];

export const isPacketVerdict = (v: string): v is PacketVerdict =>
  (PACKET_VERDICTS as readonly string[]).includes(v);

/** Body-copy words banned outside a retraction context (DESIGN_PRINCIPLES P5.3). */
export const BANNED_COPY = /\bedge\b|\bROI\b|\bprofit|\bbeats?\b|outperform|\bbets?\b|\bbetting\b|\$\s*\d/i;

/** Retracted numbers: only /evidence/retractions/ may print these. */
export const RETRACTED_TOKENS = ["+18.38%", "0.119", "+54%", "78.11", "8.94", "54.57"];
