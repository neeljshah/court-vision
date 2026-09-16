import { describe, expect, it } from "vitest";
import { resolveEntityIntent, type AtlasEntity } from "./askEntityIntent";

const atlasEntities: AtlasEntity[] = [
  { name: "Nikola Jokic", pack: "nba_players", slug: "nikola_jokic" },
  { name: "Giannis Antetokounmpo", pack: "nba_players", slug: "giannis_antetokounmpo" },
  { name: "Alex Smith", pack: "nba_players", slug: "alex_smith" },
  { name: "Alex Smith", pack: "tennis", slug: "alex_smith" },
];

describe("resolveEntityIntent", () => {
  it("resolves a single surname to its published entity", () => {
    expect(resolveEntityIntent("Jokic profile", atlasEntities).entities).toEqual([atlasEntities[0]]);
  });

  it("resolves a normalized full name", () => {
    expect(resolveEntityIntent("Nikola Jokic metrics", atlasEntities).entities).toEqual([atlasEntities[0]]);
  });

  it("recognizes a pair joined by vs", () => {
    expect(resolveEntityIntent("Jokic vs Giannis", atlasEntities)).toMatchObject({
      entities: [atlasEntities[0], atlasEntities[1]], isComparison: true,
    });
  });

  it("recognizes an unambiguous given name in a common player reference", () => {
    expect(resolveEntityIntent("Jokic Giannis", atlasEntities).entities).toEqual([atlasEntities[0], atlasEntities[1]]);
  });

  it("recognizes a pair introduced with compare and joined by and", () => {
    expect(resolveEntityIntent("Compare Nikola Jokic and Giannis Antetokounmpo", atlasEntities)).toMatchObject({
      entities: [atlasEntities[0], atlasEntities[1]], isComparison: true,
    });
  });

  it("retains ambiguous names from every pack", () => {
    const result = resolveEntityIntent("Alex Smith", atlasEntities);
    expect(result.entities).toEqual([atlasEntities[2], atlasEntities[3]]);
    expect(result.isComparison).toBe(false);
  });
});
