import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { ComparisonEntity, RawManifest } from "./comparisonData";
import { mlbAtlasFamily, mlbAtlasFamilyOptions, parseMlbAtlasFamily } from "./mlbAtlasFamily";

const entity = (sourceEntity?: string): ComparisonEntity => ({
  slug: sourceEntity || "unknown", name: sourceEntity || "Unknown", sourceEntity, values: {}, percentiles: {},
});

describe("MLB atlas families", () => {
  it("classifies only exact recognized prefixes", () => {
    expect(mlbAtlasFamily("pitch_type:FF")).toBe("pitch_type");
    expect(mlbAtlasFamily("team:CHC")).toBe("team");
    expect(mlbAtlasFamily("count:0-2")).toBe("count");
    for (const value of [undefined, "", "pitch_type:", "pitch-types:FF", "mlb_pitch_type:FF", "TEAM:CHC", "other:FF"]) {
      expect(mlbAtlasFamily(value)).toBeUndefined();
    }
  });

  it("counts the actual public families in stable display order", () => {
    const manifest = JSON.parse(readFileSync(resolve(__dirname, "../../public/data/showcase/atlas_mlb_pitch_manifest.json"), "utf8")) as RawManifest;
    const entities = manifest.entries!.map(entry => entity(entry.entity));
    expect(mlbAtlasFamilyOptions(entities)).toEqual([
      { family: "pitch_type", label: "Pitch types", count: 19 },
      { family: "team", label: "Teams", count: 30 },
      { family: "count", label: "Count states", count: 12 },
    ]);
  });

  it("keeps empty counts and safely parses query values", () => {
    expect(mlbAtlasFamilyOptions([entity("unknown:item")])).toEqual([
      { family: "pitch_type", label: "Pitch types", count: 0 },
      { family: "team", label: "Teams", count: 0 },
      { family: "count", label: "Count states", count: 0 },
    ]);
    expect(["pitch_type", "team", "count"].map(parseMlbAtlasFamily)).toEqual(["pitch_type", "team", "count"]);
    for (const value of [null, undefined, "", "pitch", "Pitch_type", "team:CHC"]) {
      expect(parseMlbAtlasFamily(value)).toBeUndefined();
    }
  });
});
