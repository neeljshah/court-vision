export type RetractionCitation = {
  document: string;
  section: string;
  date: string;
  measurementIdentity: string;
  sportsCovered: readonly string[];
  recordsWithdrawal?: boolean;
  publishedOnSite: boolean;
};

export type RelatedReading = {
  label: string;
  sourceId: string;
};

// The evidence packet is the dated, repository-level withdrawal record. It is
// intentionally not linked from the static site because it is not published there.
const NBA_WITHDRAWAL_RECORD = {
  document: "docs/JOB_EVIDENCE_PACKET.md",
  date: "2026-07-23",
  sportsCovered: ["NBA"],
  publishedOnSite: false,
} as const;

export const RETRACTION_CITATIONS = {
  "pregame-return": {
    ...NBA_WITHDRAWAL_RECORD,
    section: "Section 4, Do-not-claim list: pregame return row",
    measurementIdentity: "Withdrawal record for the pregame return calculation and its market-following defect.",
  },
  "end-of-third-quarter-brier": {
    ...NBA_WITHDRAWAL_RECORD,
    section: "Section 3, In-game win-probability Brier; Section 4, end-of-third-quarter row",
    measurementIdentity: "Withdrawal record for the leak-inflated end-of-third-quarter Brier score and its leak-free replacement.",
  },
  "in-play-proxy": {
    ...NBA_WITHDRAWAL_RECORD,
    section: "Section 4, Do-not-claim list: in-play proxy row",
    measurementIdentity: "Withdrawal record for the in-play proxy score, which used an L5 reference instead of a closing reference.",
  },
  "closing-line-movement": {
    ...NBA_WITHDRAWAL_RECORD,
    section: "Section 4, Do-not-claim list: aggregate CLV row",
    measurementIdentity: "Withdrawal record for the aggregate closing-line movement calculation and its circular comparison corpus.",
  },
  "steals-blocks-overfit": {
    ...NBA_WITHDRAWAL_RECORD,
    section: "Section 3, The self-caught leaks are the strength",
    measurementIdentity: "Withdrawal record for the steals and blocks training-versus-holdout overfit measurement.",
  },
  "assists-playoffs": {
    ...NBA_WITHDRAWAL_RECORD,
    section: "Section 3, lines 193-197: assists withdrawal record",
    measurementIdentity: "Withdrawal record for the assists conclusion after its playoff stress test.",
  },
} as const satisfies Record<string, RetractionCitation>;

export const RELATED_READING = {
  ledger: {
    label: "Claim ledger (context only; snapshot predates these withdrawals)",
    sourceId: "fwd_claim_scoreboard",
  },
  stateCalibration: {
    label: "State-conditioned calibration (MLB and international soccer only)",
    sourceId: "state_conditioned_calibration",
  },
} as const satisfies Record<string, RelatedReading>;
