// packetVerdicts.ts -- the verdict vocabulary of docs/JOB_EVIDENCE_PACKET.md
// (DESIGN_PRINCIPLES section 3). Nothing else may appear in a verdict slot. Every label has
// one meaning (calibration language only) and, where the packet attaches one, a qualifier
// that is rendered with it. components/evidence/VerdictLabel.tsx renders these.
export const PACKET_VERDICTS = [
  "TRAILS_CLOSE", "MATCHES_CLOSE", "UNDERPOWERED", "INSUFFICIENT", "PROVISIONAL",
  "MODEL_SHARPER_PROVISIONAL", "MARKET_SHARPER_PROVISIONAL", "BEHIND",
  "CONFIRMED_LOCAL", "NULL", "NOT_TESTABLE", "REJECT", "FAILED_REPLICATION",
  "REPLICATED", "RETRACTED", "SUPERSEDED", "CORRECTED",
] as const;

export type PacketVerdict = (typeof PACKET_VERDICTS)[number];

export const isPacketVerdict = (v: unknown): v is PacketVerdict =>
  typeof v === "string" && (PACKET_VERDICTS as readonly string[]).includes(v);

/** What each label licenses (title text). */
export const VERDICT_MEANING: Record<PacketVerdict, string> = {
  TRAILS_CLOSE: "Pregame: the model scores worse than the devigged close and the 95% interval on the gap excludes zero.",
  MATCHES_CLOSE: "The 95% interval on the model-minus-close gap includes zero, and the sample cannot resolve a gap below its MDE: not resolved, not parity.",
  UNDERPOWERED: "The sample cannot resolve a gap smaller than its minimum detectable effect; no direction is drawn.",
  INSUFFICIENT: "Fewer than 30 games in the cell; no verdict is drawn until it fills (packet rule).",
  PROVISIONAL: "Held once on a single corpus or fold; awaits replication on an independent corpus before it is settled.",
  MODEL_SHARPER_PROVISIONAL: "A small-sample retrospective diagnostic in which the model scored sharper than the market reference; provisional, not evidence of market outperformance.",
  MARKET_SHARPER_PROVISIONAL: "The market reference scored sharper than the model and the interval excludes zero, on a single corpus; provisional until replicated.",
  BEHIND: "In-game: the model scores worse than the contemporaneous Kalshi in-play mid on the same ticks and the 95% interval on the gap excludes zero.",
  CONFIRMED_LOCAL: "The mechanism held in its own local leak-free test, with sample size and p-value recorded; not yet replicated on an independent corpus.",
  NULL: "Tested leak-free; no effect detectable at the recorded sample size.",
  NOT_TESTABLE: "No usable data existed to test it; no proxy was invented.",
  REJECT: "Failed the leak-free gate; not used by any prediction.",
  FAILED_REPLICATION: "Held on one corpus but not on an independent one; kept and labelled, not used.",
  REPLICATED: "Held on two independent corpora, seasons or splits.",
  RETRACTED: "Withdrawn as a measurement artifact; printed only in its retraction context.",
  SUPERSEDED: "Replaced by a newer measurement; kept for the record.",
  CORRECTED: "An earlier figure was wrong and has been corrected; the correction is dated.",
};

/** The qualifier the packet attaches to the label; rendered with it by default. */
export const VERDICT_QUALIFIER: Partial<Record<PacketVerdict, string>> = {
  MATCHES_CLOSE: "underpowered",
  // ponytail: the rest of the packet wording lives in the meaning (title); "outperform" is BANNED_COPY in body text.
  MODEL_SHARPER_PROVISIONAL: "small-sample retrospective diagnostic",
  MARKET_SHARPER_PROVISIONAL: "single corpus; provisional",
  BEHIND: "vs the Kalshi in-play mid",
  PROVISIONAL: "not replicated",
  CONFIRMED_LOCAL: "local test; not replicated",
};

/** Body-copy words banned outside a retraction context (DESIGN_PRINCIPLES P5.3). */
export const BANNED_COPY = /\bedge\b|\bROI\b|\bprofit|\bbeats?\b|outperform|\bbets?\b|\bbetting\b|\$\s*\d/i;

/** Retracted numbers: only /evidence/retractions/ may print these. */
export const RETRACTED_TOKENS = ["+18.38%", "0.119", "+54%", "78.11", "8.94", "54.57"];
