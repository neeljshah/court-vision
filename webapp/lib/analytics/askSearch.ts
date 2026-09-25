// Grounded client-side retrieval for Ask Scout's committed answer corpus.
// It ranks corpus fields only; it never generates or alters an answer.
import { entityForms, normalizeEntityName, resolveEntityIntent, type AtlasEntity } from "./askEntityIntent";
export type AskStatus = "ok" | "no_data" | "refused";

export interface AskAnswer {
  status: AskStatus;
  answer: string;
  source_artifact: string;
  as_of?: string; source_module_ids?: string[];
  explore_path?: string;
}
export interface AskEntry {
  q: string;
  alt_phrasings: string[];
  tags: string[];
  bucket: string;
  a: AskAnswer;
  entity?: AtlasEntity;
}
type MatchKind = "direct" | "related" | "none" | "unavailable";

export interface ResolvedQuestion {
  entry: AskEntry | null;
  kind: MatchKind;
  followUps: string[];
  compareOffer?: { label: string; href: string };
  entityChoices?: AtlasEntity[];
}
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
const TEMPORAL_QUERY = /\b(live|latest|current|tonight|today|now|realtime|real time|next game)\b/i;
function norm(value: string): string {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function entryMentionsEntity(entry: AskEntry, entity: AtlasEntity): boolean {
  if (entry.entity?.pack === entity.pack && entry.entity.slug === entity.slug) return true;
  const searchable = normalizeEntityName(`${entry.q} ${(entry.alt_phrasings || []).join(" ")}`);
  return entityForms(entity).some((form) => ` ${searchable} `.includes(` ${form} `));
}

function supportsEntities(entry: AskEntry, entities: AtlasEntity[]): boolean {
  return entities.every((entity) => entryMentionsEntity(entry, entity));
}

function sameEntities(first: AtlasEntity[], second: AtlasEntity[]): boolean {
  return first.length === second.length && first.every((entity) => second.some(candidate =>
    candidate.pack === entity.pack && candidate.slug === entity.slug
  ));
}

function comparisonOffer(entities: AtlasEntity[]): ResolvedQuestion["compareOffer"] {
  if (entities.length !== 2 || entities[0].pack !== entities[1].pack) return undefined;
  const [first, second] = entities;
  return {
    label: `Compare ${first.name} and ${second.name}`,
    href: `/analytics/compare?pack=${encodeURIComponent(first.pack)}&a=${encodeURIComponent(first.slug)}&b=${encodeURIComponent(second.slug)}`,
  };
}

function tokens(value: string): string[] {
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

interface Candidate {
  item: IndexedEntry;
  score: number;
  matchedTerms: Set<string>;
  exactPhrase: boolean;
}

const FOLLOWUP_GENERIC = new Set([
  "nba", "mlb", "soccer", "tennis", "calibration", "player", "team", "batter",
  "pitch", "pitch_type", "type", "checkpoint", "public", "profile", "analytics", "module",
  "ok", "confirmed", "partial", "not_buildable", "derived", "analysis", "descriptive",
  "experimental", "published", "snapshot", "source", "formula", "scope", "limitations",
  "historical", "live", "forecast", "record", "data",
]);
const SPORT_TERMS = new Set(["nba", "mlb", "soccer", "tennis"]);

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

function isDirect(queryTerms: string[], candidate: Candidate, frequencies: Map<string, number>): boolean {
  if (candidate.exactPhrase) return true;
  if (queryTerms.length < 2 || hasUnmatchedSpecificTerm(queryTerms, candidate, frequencies) || hasConflictingSport(queryTerms, candidate)) return false;
  const coverage = candidate.matchedTerms.size / queryTerms.length;
  return candidate.matchedTerms.size >= 2 && coverage >= 0.6;
}

function matchesStaticQuestion(queryTerms: string[], entry: AskEntry): boolean {
  const query = new Set(queryTerms);
  return [entry.q, ...(entry.alt_phrasings || [])].some((phrase) => {
    const terms = tokens(phrase);
    return terms.length === query.size && terms.every((term) => query.has(term));
  });
}

function followUps(entries: AskEntry[], selected: AskEntry, queryTerms: string[], entities: AtlasEntity[]): string[] {
  const publishedEntities = entries.flatMap((entry) => entry.entity ? [entry.entity] : []);
  const selectedEntities = entities.length ? entities : resolveEntityIntent(selected.q, publishedEntities).entities;
  const selectedTerms = new Set(
    tokens(`${selected.q} ${selected.alt_phrasings.join(" ")} ${selected.tags.join(" ")}`)
  );
  const selectedSpecific = Array.from(selectedTerms).filter((term) => !FOLLOWUP_GENERIC.has(term) && !SPORT_TERMS.has(term));
  const selectedSports = new Set(tokens(selected.tags.join(" ")).filter((term) => SPORT_TERMS.has(term)));
  const ranked = entries
    .filter((entry) => entry.q !== selected.q && entry.a.status === "ok" &&
      (!selected.a.explore_path || entry.a.source_artifact === selected.a.source_artifact) &&
      (!entry.entity || supportsEntities(entry, entities)))
    .map((entry) => {
      const entryTerms = new Set(tokens(`${entry.q} ${entry.alt_phrasings.join(" ")} ${entry.tags.join(" ")}`));
      const entrySports = new Set(Array.from(entryTerms).filter((term) => SPORT_TERMS.has(term)));
      const hasSportConflict = selectedSports.size > 0 && entrySports.size > 0 &&
        !Array.from(selectedSports).some((sport) => entrySports.has(sport));
      const sharedSpecific = selectedSpecific.filter((term) => entryTerms.has(term)).length;
      const sharedQuery = queryTerms.filter((term) => !FOLLOWUP_GENERIC.has(term) && entryTerms.has(term)).length;
      const sameSource = entry.a.source_artifact === selected.a.source_artifact;
      const sameSport = Array.from(selectedSports).some((sport) => entrySports.has(sport));
      const hasContext = sameSource || sharedSpecific + sharedQuery > 0;
      const score = hasSportConflict || !hasContext
        ? 0
        : (sameSource ? 40 : 0) + sharedSpecific * 8 + sharedQuery * 2 + (sameSport ? 1 : 0);
      return { entry, score };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.entry.q.localeCompare(b.entry.q));
  const skipEntityResolution = !entities.length && !selectedEntities.length;
  const result: string[] = [];
  for (const { entry } of ranked) {
    if (!skipEntityResolution) {
      const entryEntities = resolveEntityIntent(entry.q, publishedEntities).entities;
      const entityFree = !entry.entity && !entryEntities.length;
      if (!(entityFree || supportsEntities(entry, entities)) ||
        (selectedEntities.length > 0 && entryEntities.length > 0 && !sameEntities(entryEntities, selectedEntities))) continue;
    }
    result.push(entry.q);
    if (result.length === 3) break;
  }
  return result;
}

export function resolveQuestion(query: string, entries: AskEntry[]): ResolvedQuestion | null {
  const queryTerms = tokens(query);
  if (!queryTerms.length) return null;
  if (!entries.length) return { entry: null, kind: "unavailable", followUps: [] };
  const intent = resolveEntityIntent(query, entries.flatMap((entry) => entry.entity ? [entry.entity] : []));
  if (intent.candidates.length) return {
    entry: null,
    kind: "none",
    followUps: [],
    entityChoices: intent.candidates,
  };
  const offer = intent.isComparison ? comparisonOffer(intent.entities) : undefined;

  // Exact published answers include missing coverage for named metrics such as
  // Live-Clock Fraction. Other live/latest requests still use the scope refusal.
  const staticExact = entries.find((entry) => entry.a.status !== "refused" &&
    supportsEntities(entry, intent.entities) && matchesStaticQuestion(queryTerms, entry));
  if (staticExact) return {
    entry: staticExact,
    kind: offer ? "related" : "direct",
    followUps: followUps(entries, staticExact, queryTerms, intent.entities),
    compareOffer: offer,
  };
  if (TEMPORAL_QUERY.test(query) && !staticExact) {
    const scope = entries.find((entry) =>
      entry.a.status === "no_data" && entry.tags.includes("live") && entry.tags.includes("scope")
    );
    if (scope) return { entry: scope, kind: "direct", followUps: [] };
  }

  const indexed = indexEntries(entries);
  const frequencies = new Map<string, number>();
  indexed.forEach((item) => {
    new Set([...item.question, ...item.alternate, ...item.tags, ...item.answer]).forEach((term) => {
      frequencies.set(term, (frequencies.get(term) || 0) + 1);
    });
  });
  const eligible = intent.entities.length ? indexed.filter((item) => supportsEntities(item.entry, intent.entities)) : indexed;
  const best = eligible
    .map((item) => candidateFor(query, queryTerms, item, frequencies))
    .sort((a, b) => b.score - a.score || a.item.entry.q.localeCompare(b.item.entry.q))[0];

  if (!best || best.matchedTerms.size === 0) return { entry: null, kind: "none", followUps: [], compareOffer: offer };
  const entry = best.item.entry;
  return {
    entry,
    kind: offer ? "related" : isDirect(queryTerms, best, frequencies) ? "direct" : "related",
    followUps: followUps(entries, entry, queryTerms, intent.entities),
    compareOffer: offer,
  };
}
