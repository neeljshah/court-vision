export interface ClaimHistoryRun {
  verdict: string;
  status: string;
  runTs: string | null;
  corpus: string | null;
  n: number | null;
  effect: number | null;
}

export interface ClaimHistoryFamily {
  sport: string;
  hypothesis: string;
  currentStatus: string;
  verdictSequence: string[];
  history: ClaimHistoryRun[];
  flipped: boolean;
}

export interface ClaimHistoryLedger {
  families: ClaimHistoryFamily[];
  flippedFamilies: ClaimHistoryFamily[];
  runCount: number;
  undatedRunCount: number;
  asOf: string | null;
  byStatus: Record<string, number>;
}

type RecordValue = Record<string, unknown>;

function record(value: unknown): RecordValue | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function runFrom(value: unknown): ClaimHistoryRun | null {
  const source = record(value);
  const verdict = text(source?.verdict);
  const status = text(source?.status);
  if (!verdict || !status) return null;
  return {
    verdict,
    status,
    runTs: text(source?.run_ts),
    corpus: text(source?.corpus),
    n: finite(source?.n),
    effect: finite(source?.effect),
  };
}

function familyFrom(value: unknown): ClaimHistoryFamily | null {
  const source = record(value);
  const sport = text(source?.sport);
  const hypothesis = text(source?.hypothesis);
  const currentStatus = text(source?.current_status);
  if (!sport || !hypothesis || !currentStatus || !Array.isArray(source?.history)) return null;
  const history = source.history.flatMap(item => {
    const parsed = runFrom(item);
    return parsed ? [parsed] : [];
  });
  if (!history.length) return null;
  const verdictSequence = Array.isArray(source.verdict_sequence)
    ? source.verdict_sequence.flatMap(item => {
      const verdict = text(item);
      return verdict ? [verdict] : [];
    })
    : history.map(run => run.verdict);
  return { sport, hypothesis, currentStatus, verdictSequence, history, flipped: source.flipped === true };
}

/** Builds the source-ordered rerun ledger; entries are deliberately never date-sorted. */
export function buildClaimHistory(value: unknown): ClaimHistoryLedger {
  const source = record(value);
  const families = Array.isArray(source?.families) ? source.families.flatMap(item => {
    const parsed = familyFrom(item);
    return parsed ? [parsed] : [];
  }) : [];
  const runs = families.flatMap(family => family.history);
  const summary = record(source?.summary);
  const publishedStatuses = record(summary?.by_status);
  const byStatus = Object.fromEntries(Object.entries(publishedStatuses || {}).flatMap(([key, item]) => {
    const count = finite(item);
    return count === null || count < 0 ? [] : [[key, Math.trunc(count)]];
  }));
  return {
    families,
    flippedFamilies: families.filter(family => family.flipped),
    runCount: runs.length,
    undatedRunCount: runs.filter(run => run.runTs === null).length,
    asOf: text(source?.as_of),
    byStatus,
  };
}

/** Stable document id shared by the server-rendered flip links and client ledger. */
export function claimFamilyId(family: Pick<ClaimHistoryFamily, "sport" | "hypothesis">): string {
  return `claim-family-${encodeURIComponent(family.sport)}-${encodeURIComponent(family.hypothesis)}`;
}

export function claimFamilyLabel(family: Pick<ClaimHistoryFamily, "hypothesis">): string {
  return family.hypothesis.replaceAll("_", " ");
}

/** Returns only flip links that resolve to a rendered family in this ledger. */
export function flipDestinations(ledger: ClaimHistoryLedger): ClaimHistoryFamily[] {
  const familyKeys = new Set(ledger.families.map(family => `${family.sport}|${family.hypothesis}`));
  return ledger.flippedFamilies.filter(family => familyKeys.has(`${family.sport}|${family.hypothesis}`));
}
