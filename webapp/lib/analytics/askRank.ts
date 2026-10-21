// Ranking primitives for Ask Scout's prepared-answer corpus: tokenization,
// per-entry scoring and the direct-versus-related decision. Pure functions over
// committed text; nothing here generates or alters an answer.
import type { AskEntry } from "./askSearch";

const STOP = new Set(
  ("the a an is are was were be it of to do does did what how why when who which for " +
    "on in at by vs and or my you your me i can will would should tell about any this " +
    "that with as from has have not no there show give look get really actually").split(" ")
);
const ALIASES: Record<string, string> = {
  assists: "assist",
  accurate: "accuracy",
  accuracy: "accuracy",
  basketball: "nba",
  calibrated: "calibration",
  calibrate: "calibration",
  calibration: "calibration",
  comparisons: "compare",
  compared: "compare",
  comparing: "compare",
  forecasts: "prediction",
  mlb: "mlb",
  models: "model",
  nba: "nba",
  odds: "market",
  passer: "playmaking",
  passing: "playmaking",
  playmaker: "playmaking",
  predictions: "prediction",
  probabilities: "probability",
  soccer: "soccer",
  stats: "stat",
};
export const SPORT_TERMS = new Set(["nba", "mlb", "soccer", "tennis"]);

export function norm(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function tokens(value: string): string[] {
  return Array.from(
    new Set(
      norm(value)
        .split(" ")
        .map((term) => ALIASES[term] || term)
        .filter((term) => term.length > 1 && !STOP.has(term))
    )
  );
}

interface IndexedEntry {
  entry: AskEntry;
  question: Set<string>;
  alternate: Set<string>;
  tags: Set<string>;
  answer: Set<string>;
  phrasings: string[];
}

export interface Candidate {
  item: IndexedEntry;
  score: number;
  matchedTerms: Set<string>;
  exactPhrase: boolean;
}

export interface RankedQuery {
  /** Every eligible entry, best first; ties break on the question text. */
  candidates: Candidate[];
  /** Document frequency of each term across the eligible entries. */
  frequencies: Map<string, number>;
}

function indexEntries(entries: AskEntry[]): IndexedEntry[] {
  return entries.map((entry) => ({
    entry,
    question: new Set(tokens(entry.q)),
    alternate: new Set((entry.alt_phrasings || []).flatMap(tokens)),
    tags: new Set((entry.tags || []).flatMap(tokens)),
    answer: new Set(tokens(entry.a.answer)),
    phrasings: [norm(entry.q), ...(entry.alt_phrasings || []).map(norm)],
  }));
}

function termWeight(term: string, frequency: number): number {
  // Specific entity names should decide a result before generic domain words do.
  const specificity = frequency <= 3 ? 4 : frequency <= 10 ? 2.5 : 1;
  return term.length >= 7 ? specificity + 0.5 : specificity;
}

function candidateFor(query: string, terms: string[], item: IndexedEntry, frequencies: Map<string, number>): Candidate {
  const queryNorm = norm(query);
  const matchedTerms = new Set<string>();
  let score = 0;
  for (const term of terms) {
    const weight = termWeight(term, frequencies.get(term) || 1);
    if (item.question.has(term)) {
      score += 5 * weight;
      matchedTerms.add(term);
    }
    if (item.alternate.has(term)) {
      score += 4 * weight;
      matchedTerms.add(term);
    }
    if (item.tags.has(term)) {
      score += 4.5 * weight;
      matchedTerms.add(term);
    }
    if (item.answer.has(term)) {
      score += 1.5 * weight;
      matchedTerms.add(term);
    }
  }
  // A substring match is not an exact answer: "Tell me about Ohtani basketball
  // rebounds" must not bypass the sport/metric checks just because "tell me
  // about ohtani" is an alternate phrasing.
  const exactPhrase = item.phrasings.some((phrase) => phrase === queryNorm);
  if (exactPhrase) score += 60;
  return { item, score, matchedTerms, exactPhrase };
}

/**
 * Score every eligible entry against the query and sort best first. Term
 * frequencies come from the whole searchable corpus, so an entity-scoped query
 * keeps the same specificity thresholds as an open one.
 */
export function rankEntries(query: string, queryTerms: string[], entries: AskEntry[], eligible: (entry: AskEntry) => boolean = () => true): RankedQuery {
  const indexed = indexEntries(entries);
  const frequencies = new Map<string, number>();
  indexed.forEach((item) => {
    new Set([...item.question, ...item.alternate, ...item.tags, ...item.answer]).forEach((term) => {
      frequencies.set(term, (frequencies.get(term) || 0) + 1);
    });
  });
  const candidates = indexed
    .filter((item) => eligible(item.entry))
    .map((item) => candidateFor(query, queryTerms, item, frequencies))
    .sort((a, b) => b.score - a.score || a.item.entry.q.localeCompare(b.item.entry.q));
  return { candidates, frequencies };
}

/**
 * The prepared questions nearest to a query that had no direct answer: ranked
 * candidates that share at least one term, at most `limit`. These are offered as
 * topics to open, never shown as if their answers addressed the query.
 */
export function closestQuestions(candidates: Candidate[], limit = 3, exclude: ReadonlySet<string> = new Set()): string[] {
  const out: string[] = [];
  for (const candidate of candidates) {
    if (candidate.matchedTerms.size === 0) break;
    const question = candidate.item.entry.q;
    if (exclude.has(question) || out.includes(question)) continue;
    out.push(question);
    if (out.length === limit) break;
  }
  return out;
}

function hasUnmatchedSpecificTerm(queryTerms: string[], candidate: Candidate, frequencies: Map<string, number>): boolean {
  return queryTerms.some((term) =>
    term.length >= 4 && (frequencies.get(term) || 0) <= 20 && !candidate.matchedTerms.has(term)
  );
}

function hasConflictingSport(queryTerms: string[], candidate: Candidate): boolean {
  const querySports = queryTerms.filter((term) => SPORT_TERMS.has(term));
  const candidateSports = Array.from(candidate.item.tags).filter((term) => SPORT_TERMS.has(term));
  return candidateSports.length > 0 && querySports.some((term) => !candidateSports.includes(term));
}

/** Whether the best candidate answers the query, or is merely the nearest entry. */
export function isDirect(queryTerms: string[], candidate: Candidate, frequencies: Map<string, number>): boolean {
  if (candidate.exactPhrase) return true;
  if (queryTerms.length < 2 || hasUnmatchedSpecificTerm(queryTerms, candidate, frequencies) || hasConflictingSport(queryTerms, candidate)) return false;
  const coverage = candidate.matchedTerms.size / queryTerms.length;
  return candidate.matchedTerms.size >= 2 && coverage >= 0.6;
}
