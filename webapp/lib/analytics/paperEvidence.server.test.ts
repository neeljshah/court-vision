import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { fieldPathExists, resolveEvidenceArtifact, validatePaperEvidence } from "./paperEvidence.server";
import { paperReferences, publishedArtifacts } from "./papers.server";

function sample(): Record<string, unknown> {
  return JSON.parse(readFileSync(join(process.cwd(), "public", "data", "papers", "how-to-read-a-courtvision-paper.json"), "utf8")) as Record<string, unknown>;
}

const artifacts = publishedArtifacts();
const references = paperReferences();

describe("paper evidence resolution", () => {
  it("names a nonexistent field path in the validation reason", () => {
    const paper = sample();
    const evidence = paper.evidence as Array<{ fields: string[] }>;
    evidence[0].fields = ["sports.mlb.sides.model_prob.not_published"];
    expect(validatePaperEvidence(paper, artifacts, references)).toMatch(/sports\.mlb\.sides\.model_prob\.not_published/);
  });

  it("prefers showcase for an ambiguous basename unless evidence names insights", () => {
    const entry = { artifact: "calibration_stability.json", module: "calibration_stability", asOf: null, fields: ["id"] };
    expect(resolveEvidenceArtifact(entry)?.directory).toBe("showcase");
    expect(resolveEvidenceArtifact({ ...entry, path: "insights" })?.directory).toBe("insights");
  });

  it("rejects unknown analysis, finding and paper targets", () => {
    for (const kind of ["analysis", "finding", "paper"] as const) {
      const paper = sample();
      paper.related = [{ kind, id: "not-a-registered-target" }];
      expect(validatePaperEvidence(paper, artifacts, references)).toMatch(new RegExp(`related ${kind}`));
    }
  });

  it("rejects duplicate section ids", () => {
    const paper = sample();
    const sections = paper.sections as Array<{ id: string }>;
    sections[1].id = sections[0].id;
    expect(validatePaperEvidence(paper, artifacts, references)).toMatch(/duplicate section id/);
  });

  it("resolves wildcards, key-value selectors and keyed brackets", () => {
    const value = {
      sports: { mlb: { buckets: [{ n: 10 }, { n: 20 }] } },
      pitch_type_distribution: [{ pitch_type: "FF", n: 42 }],
      counts: [{ balls: 0, strikes: 0, n: 18 }],
      by_class: { three_ball: { prob_matrix: { FF: { FF: 0.25 } } } },
    };
    expect(fieldPathExists(value, "sports.mlb.buckets[].n")).toBe(true);
    expect(fieldPathExists(value, "pitch_type_distribution[pitch_type=FF].n")).toBe(true);
    expect(fieldPathExists(value, "counts[balls=0,strikes=0].n")).toBe(true);
    expect(fieldPathExists(value, "by_class[three_ball].prob_matrix[FF][FF]")).toBe(true);
  });

  it("resolves quoted bracket keys and rejects placeholders with guidance", () => {
    expect(fieldPathExists({ grains: { "early(inn1-3)": { n: 10 } } }, 'grains["early(inn1-3)"].n')).toBe(true);
    const paper = sample();
    const evidence = paper.evidence as Array<{ fields: string[] }>;
    evidence[0].fields = ["sports.<sport>.n_series_used"];
    expect(validatePaperEvidence(paper, artifacts, references)).toMatch(/unsupported placeholder; use \[\] wildcard syntax/);
  });
  it("resolves dots inside selectors and numeric array indexes", () => {
    const value = {
      grains: { "early(inn1-3)": { ".4-.6": { n: 12 } } },
      move_by_bucket: { "6h+": { n: 8 } },
      rows: [{ n: 3 }],
      cells: [{ bucket: "lead_00|ot|ot", n: 80 }],
    };
    expect(fieldPathExists(value, "grains[early(inn1-3)][.4-.6].n")).toBe(true);
    expect(fieldPathExists(value, "move_by_bucket[6h+].n")).toBe(true);
    expect(fieldPathExists(value, "rows[0].n")).toBe(true);
    expect(fieldPathExists(value, "cells[bucket=lead_00|ot|ot].n")).toBe(true);
    expect(fieldPathExists(value, "rows[1].n")).toBe(false);
  });
  it("rejects malformed paths, prose and inherited properties", () => {
    const inherited = Object.create({ hidden: { value: 1 } }) as Record<string, unknown>;
    inherited.rows = [Object.create({ hidden: 1 })];
    for (const path of ["a..b", "a[b", "a]b", "a[nested[key]]", "rows[0] prose", "rows[-1]"]) {
      expect(fieldPathExists({ a: {}, rows: [] }, path)).toBe(false);
    }
    expect(fieldPathExists(inherited, "hidden.value")).toBe(false);
    expect(fieldPathExists(inherited, "rows[0][hidden]")).toBe(false);
  });
});
