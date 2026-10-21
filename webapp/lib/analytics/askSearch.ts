// Grounded client-side retrieval for Ask Scout's committed answer corpus.
// It ranks corpus fields only; it never generates or alters an answer. A query
// without a direct match gets no answer text, only the closest prepared questions.
import { entityForms, normalizeEntityName, resolveEntityIntent, type AtlasEntity } from "./askEntityIntent";
import { closestQuestions, isDirect, norm, rankEntries, SPORT_TERMS, tokens } from "./askRank";
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
  exactOnly?: boolean;
}
/** direct: the entry answers the query. related: nothing answers it; `entry` is
 *  only the nearest prepared question and must not be shown as an answer. */
type MatchKind = "direct" | "related" | "none" | "unavailable";
export interface ResolvedQuestion {
  entry: AskEntry | null;
  kind: MatchKind;
  followUps: string[];
  /** Prepared questions nearest to an unanswered query (related/none), best first. */
  closest: string[];
  compareOffer?: { label: string; href: string };
  entityChoices?: AtlasEntity[];
}
const TEMPORAL_QUERY = /\b(live|latest|current|tonight|today|now|realtime|real time|next game)\b/i;

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

const FOLLOWUP_GENERIC = new Set([
  "nba", "mlb", "soccer", "tennis", "calibration", "player", "team", "batter",
  "pitch", "pitch_type", "type", "checkpoint", "public", "profile", "analytics", "module",
  "ok", "confirmed", "partial", "not_buildable", "derived", "analysis", "descriptive",
  "experimental", "published", "snapshot", "source", "formula", "scope", "limitations",
  "historical", "live", "forecast", "record", "data",
]);

function matchesStaticQuestion(queryTerms: string[], entry: AskEntry, queryText: string): boolean {
  if (entry.exactOnly) return !TEMPORAL_QUERY.test(queryText) && [entry.q, ...entry.alt_phrasings].some(phrase => norm(phrase) === norm(queryText));
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
    .filter((entry) => !entry.exactOnly && entry.q !== selected.q && entry.a.status === "ok" &&
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
  if (!entries.length) return { entry: null, kind: "unavailable", followUps: [], closest: [] };
  const intent = resolveEntityIntent(query, entries.flatMap((entry) => entry.entity ? [entry.entity] : []));
  if (intent.candidates.length) return {
    entry: null,
    kind: "none",
    followUps: [],
    closest: [],
    entityChoices: intent.candidates,
  };
  const offer = intent.isComparison ? comparisonOffer(intent.entities) : undefined;

  const exactRefusal = entries.find((entry) => entry.a.status === "refused" && supportsEntities(entry, intent.entities) &&
    [entry.q, ...entry.alt_phrasings].some((phrase) => norm(phrase) === norm(query)));
  const staticExact = exactRefusal || entries.find((entry) => entry.a.status !== "refused" &&
    supportsEntities(entry, intent.entities) && matchesStaticQuestion(queryTerms, entry, query));
  if (staticExact) return {
    entry: staticExact,
    kind: offer ? "related" : "direct",
    followUps: offer ? [] : followUps(entries, staticExact, queryTerms, intent.entities),
    closest: offer ? [staticExact.q] : [],
    compareOffer: offer,
  };
  if (TEMPORAL_QUERY.test(query) && !staticExact) {
    const scope = entries.find((entry) =>
      entry.a.status === "no_data" && entry.tags.includes("live") && entry.tags.includes("scope")
    );
    if (scope) return { entry: scope, kind: "direct", followUps: [], closest: [] };
  }

  const searchable = entries.filter(entry => !entry.exactOnly);
  const eligible = (entry: AskEntry) => !intent.entities.length || supportsEntities(entry, intent.entities);
  const { candidates, frequencies } = rankEntries(query, queryTerms, searchable, eligible);
  const best = candidates[0];

  if (!best || best.matchedTerms.size === 0) return { entry: null, kind: "none", followUps: [], closest: [], compareOffer: offer };
  const entry = best.item.entry;
  const direct = !offer && isDirect(queryTerms, best, frequencies);
  return {
    entry,
    kind: direct ? "direct" : "related",
    followUps: direct ? followUps(entries, entry, queryTerms, intent.entities) : [],
    closest: direct ? [] : closestQuestions(candidates),
    compareOffer: offer,
  };
}
