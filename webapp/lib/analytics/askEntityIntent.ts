// Entity recognition for Scout's published Atlas records. This only identifies
// named records; it does not infer a metric, comparison, or answer.

export type AtlasEntity = {
  name: string;
  pack: string;
  slug: string;
};

export type EntityIntent = {
  entities: AtlasEntity[];
  candidates: AtlasEntity[];
  isComparison: boolean;
};

const COMMON_IDENTIFIERS = new Set([
  "away", "baseball", "basketball", "batter", "count", "home", "mlb", "nba",
  "pitch", "player", "soccer", "sport", "stat", "stats", "team", "tennis", "type",
]);

export function normalizeEntityName(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function fullEntityForms(entity: AtlasEntity): string[] {
  const publishedName = normalizeEntityName(entity.name);
  if (entity.pack !== "tennis" || !/\s+\((ATP|WTA)\)\s*$/i.test(entity.name)) {
    return [publishedName];
  }
  const playerName = normalizeEntityName(entity.name.replace(/\s+\((ATP|WTA)\)\s*$/i, ""));
  return Array.from(new Set([publishedName, playerName]));
}

export function entityForms(entity: AtlasEntity): string[] {
  const fullNames = fullEntityForms(entity);
  const nameParts = fullNames.at(-1)!.split(" ");
  const surname = nameParts.at(-1) || "";
  const givenName = nameParts.length > 1 ? nameParts[0] : "";
  // A numeric suffix in a count/metric label is not a person's name alias.
  const aliases = [surname, givenName].filter(form => /[a-z]/.test(form));
  return Array.from(new Set([...fullNames, ...aliases].filter(Boolean)));
}

function matchPosition(query: string, form: string): number {
  return ` ${query} `.indexOf(` ${form} `);
}

function entityKey(entity: AtlasEntity): string {
  return `${entity.pack}:${entity.slug}`;
}

function sortMatches(matches: { entity: AtlasEntity; position: number }[]): AtlasEntity[] {
  return matches
    .sort((a, b) => a.position - b.position)
    .map(({ entity }) => entity);
}

function atlasStopList(atlasEntities: AtlasEntity[]): Set<string> {
  const appearances = new Map<string, number>();
  atlasEntities.forEach((entity) => {
    new Set(normalizeEntityName(entity.name).split(" ").filter(Boolean)).forEach((token) => {
      appearances.set(token, (appearances.get(token) || 0) + 1);
    });
  });
  return new Set([...COMMON_IDENTIFIERS, ...Array.from(appearances)
    .filter(([, count]) => count > 25)
    .map(([token]) => token)]);
}

function hasComparisonCue(query: string): boolean {
  return /\b(compare|vs|versus)\b/.test(query) || /\band\b/.test(query);
}

export function resolveEntityIntent(query: string, atlasEntities: AtlasEntity[]): EntityIntent {
  const normalizedQuery = normalizeEntityName(query);
  if (!normalizedQuery) return { entities: [], candidates: [], isComparison: false };

  const stopList = atlasStopList(atlasEntities);
  const possibleFullMatches = atlasEntities.flatMap((entity) => {
    const forms = fullEntityForms(entity);
    return forms.flatMap((fullName, formIndex) => {
      const position = matchPosition(normalizedQuery, fullName);
      return position >= 0 ? [{ entity, position, fullName, isPublished: formIndex === 0 }] : [];
    });
  });
  const exactQualifiedNames = new Set(possibleFullMatches
    .filter(({ entity, isPublished }) => isPublished && fullEntityForms(entity).length > 1)
    .map(({ entity }) => fullEntityForms(entity)[1]));
  const fullMatches = possibleFullMatches.filter(({ entity, fullName, isPublished }) =>
    !exactQualifiedNames.has(fullName) || (isPublished && fullEntityForms(entity).length > 1));
  const consumedAliases = new Set(fullMatches.flatMap(({ entity }) => {
    const forms = entityForms(entity);
    return forms.slice(fullEntityForms(entity).length);
  }));
  const resolved = new Map<string, { entity: AtlasEntity; position: number }>();
  const ambiguous = new Map<string, { entity: AtlasEntity; position: number }>();

  fullMatches.forEach(({ entity, position, fullName }) => {
    const sameName = fullMatches.filter((match) => match.fullName === fullName);
    const target = sameName.length === 1 ? resolved : ambiguous;
    target.set(entityKey(entity), { entity, position });
  });

  const aliases = new Map<string, { entity: AtlasEntity; position: number; isGivenName: boolean }[]>();
  atlasEntities.forEach((entity) => {
    const forms = entityForms(entity);
    forms.slice(fullEntityForms(entity).length).forEach((form, index) => {
      if (stopList.has(form) || consumedAliases.has(form)) return;
      const position = matchPosition(normalizedQuery, form);
      if (position < 0) return;
      const matches = aliases.get(form) || [];
      matches.push({ entity, position, isGivenName: index === 1 });
      aliases.set(form, matches);
    });
  });

  aliases.forEach((matches) => {
    const distinct = Array.from(new Map(matches.map((match) => [entityKey(match.entity), match])).values());
    const isGivenName = distinct.some((match) => match.isGivenName);
    // A given-name alias that identifies exactly one published entity resolves; several -> a choice.
    const target = distinct.length > 1 ? ambiguous : resolved;
    distinct.forEach(({ entity, position }) => {
      if (!resolved.has(entityKey(entity))) target.set(entityKey(entity), { entity, position });
    });
  });

  const entities = sortMatches(Array.from(resolved.values()));
  const candidates = sortMatches(Array.from(ambiguous.values()).filter(({ entity }) => !resolved.has(entityKey(entity))));
  // Two resolved identities and nothing else in the query ("Jokic Giannis") is a pair request too.
  const leftover = entities
    .reduce((text, entity) => entityForms(entity).reduce((inner, form) => inner.replace(form, " "), text), normalizedQuery)
    .replace(/(compare|vs|versus|and)/g, " ")
    .trim();
  return {
    entities,
    candidates,
    isComparison: candidates.length === 0 && entities.length === 2 && (hasComparisonCue(normalizedQuery) || leftover.length === 0),
  };
}
