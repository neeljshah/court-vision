import { describe, expect, it } from "vitest";
import { resolveEntityIntent, type AtlasEntity } from "./askEntityIntent";

const atlasEntities: AtlasEntity[] = [
  { name: "Nikola Jokic", pack: "nba_players", slug: "nikola_jokic" },
  { name: "Giannis Antetokounmpo", pack: "nba_players", slug: "giannis_antetokounmpo" },
  { name: "Stephen Curry", pack: "nba_players", slug: "stephen_curry" },
  { name: "Seth Curry", pack: "nba_players", slug: "seth_curry" },
  { name: "Alex Smith", pack: "nba_players", slug: "alex_smith" },
  { name: "Alex Smith", pack: "tennis", slug: "alex_smith" },
];

describe("resolveEntityIntent", () => {
  it("does not treat numeric count suffixes as ambiguous name aliases", () => {
    const counts = ["count:0-0", "count:3-0", "count:0-2"].map(name => ({
      name, pack: "mlb_pitch_types", slug: name.replace(/:/g, "_"),
    }));
    expect(resolveEntityIntent("compare MLB counts 3-0 and 0-2", counts)).toEqual({
      entities: [], candidates: [], isComparison: false,
    });
    expect(resolveEntityIntent("count:3-0 profile", counts)).toMatchObject({
      entities: [counts[1]], candidates: [],
    });
  });

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

  it("treats two bare resolved identities as a pair, but not when other words remain", () => {
    expect(resolveEntityIntent("Jokic Giannis", atlasEntities)).toMatchObject({
      entities: [atlasEntities[0], atlasEntities[1]], candidates: [], isComparison: true,
    });
    expect(resolveEntityIntent("Jokic Giannis rebounds", atlasEntities).isComparison).toBe(false);
  });

  it("recognizes a pair introduced with compare and joined by and", () => {
    expect(resolveEntityIntent("Compare Nikola Jokic and Giannis Antetokounmpo", atlasEntities)).toMatchObject({
      entities: [atlasEntities[0], atlasEntities[1]], isComparison: true,
    });
  });

  it("retains ambiguous names from every pack", () => {
    const result = resolveEntityIntent("Alex Smith", atlasEntities);
    expect(result.entities).toEqual([]);
    expect(result.candidates).toEqual([atlasEntities[4], atlasEntities[5]]);
    expect(result.isComparison).toBe(false);
  });

  it("lets a full name consume matching first-name and surname aliases", () => {
    expect(resolveEntityIntent("Stephen Curry", atlasEntities)).toMatchObject({
      entities: [atlasEntities[2]], candidates: [], isComparison: false,
    });
  });

  it("resolves an explicit full-name comparison without short-name ambiguity", () => {
    expect(resolveEntityIntent("Compare Nikola Jokic and Giannis Antetokounmpo", atlasEntities)).toMatchObject({
      entities: [atlasEntities[0], atlasEntities[1]], candidates: [], isComparison: true,
    });
  });

  it("returns choices for a shared surname and resolves a given name that identifies one entity", () => {
    expect(resolveEntityIntent("Curry", atlasEntities).candidates).toEqual([atlasEntities[2], atlasEntities[3]]);
    expect(resolveEntityIntent("Nikola", atlasEntities)).toMatchObject({
      entities: [atlasEntities[0]], candidates: [], isComparison: false,
    });
  });

  it("does not treat common sport words as entity aliases", () => {
    expect(resolveEntityIntent("pitch velocity", [
      { name: "Pitch Type FF", pack: "mlb_pitch", slug: "pitch_type_ff" },
    ])).toMatchObject({ entities: [], candidates: [], isComparison: false });
  });
});
