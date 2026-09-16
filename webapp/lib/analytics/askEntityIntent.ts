// Entity recognition for Scout's published Atlas records. This only identifies
// named records; it does not infer a metric, comparison, or answer.

export type AtlasEntity = {
  name: string;
  pack: string;
  slug: string;
};

export type EntityIntent = {
  entities: AtlasEntity[];
  isComparison: boolean;
};

export function normalizeEntityName(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function entityForms(entity: AtlasEntity): string[] {
  const fullName = normalizeEntityName(entity.name);
  const nameParts = fullName.split(" ");
  const surname = nameParts.at(-1) || "";
  const givenName = nameParts.length > 1 ? nameParts[0] : "";
  return Array.from(new Set([fullName, surname, givenName].filter(Boolean)));
}

function matchPosition(query: string, entity: AtlasEntity): number {
  return entityForms(entity).reduce((first, form) => {
    const position = ` ${query} `.indexOf(` ${form} `);
    return position >= 0 && (first < 0 || position < first) ? position : first;
  }, -1);
}

export function resolveEntityIntent(query: string, atlasEntities: AtlasEntity[]): EntityIntent {
  const normalizedQuery = normalizeEntityName(query);
  const seen = new Set<string>();
  const matches = atlasEntities.flatMap((entity) => {
    const position = matchPosition(normalizedQuery, entity);
    if (position < 0) return [];
    const key = `${entity.pack}:${entity.slug}`;
    if (seen.has(key)) return [];
    seen.add(key);
    return [{ entity, position }];
  }).sort((a, b) => a.position - b.position || a.entity.name.localeCompare(b.entity.name));
  const entities = matches.map((match) => match.entity);
  const mentionedNames = new Set(matches.map((match) => match.position)).size;
  const hasComparisonWord = /\b(compare|vs|versus)\b/.test(normalizedQuery);
  const hasAndPair = mentionedNames === 2 && /\band\b/.test(normalizedQuery);
  const hasImplicitPair = mentionedNames === 2 && !hasComparisonWord && !hasAndPair;
  return { entities, isComparison: mentionedNames === 2 && (hasComparisonWord || hasAndPair || hasImplicitPair) };
}
