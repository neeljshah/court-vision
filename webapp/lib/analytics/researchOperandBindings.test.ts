import { describe, expect, it } from "vitest";
import { resolveResearchOperands } from "./researchOperandBindings";
import type { ResearchAnalysis, ResearchRow } from "./researchTypes";
import { basketballResearch } from "./researchBasketball";
import { getTennisGrassSupportResearch } from "./researchTennisGrassSupport";
import { buildBrierSkillScoresResearch } from "./researchBrierSkillScores";
import brierSource from "@/public/data/showcase/brier_skill_scores.json";

const analysis = (bindings?: ResearchAnalysis["bindings"]): ResearchAnalysis => ({
  id: "binding-test", title: "Binding test", sport: "nba", category: "Test", source: "test", description: "Test", scope: "Test", caveat: "Test", status: "Test",
  fields: [{ key: "games", label: "Games", unit: "number" }], rows: [], formula: "Test", interpretation: "Test", references: [], novelty: "Derived analysis", bindings,
});
const row = (values: ResearchRow["values"]): ResearchRow => ({ id: "row", label: "Row", group: "Test", values });

describe("research operand bindings", () => {
  it("resolves an exact valueKey without matching a display label", () => {
    const operands = resolveResearchOperands(analysis([{ operand: "n_games", sourcePath: "cells[].n_games", valueKey: "games", label: "Games" }]), row({ games: 42 }));
    expect(operands).toEqual([{ label: "Games", value: 42, sourcePath: "cells[].n_games", resolved: true }]);
  });

  it("does not confuse n_games with a similarly named games value", () => {
    const operands = resolveResearchOperands(analysis([{ operand: "n_games", sourcePath: "cells[].n_games", valueKey: "n_games", label: "Published games" }]), row({ games: 42 }));
    expect(operands[0]).toMatchObject({ value: null, resolved: false });
  });

  it("marks a missing published value as unresolved", () => {
    const operands = resolveResearchOperands(analysis([{ operand: "rate", sourcePath: "cells[].rate", valueKey: "rate", label: "Rate" }]), row({ rate: null }));
    expect(operands[0]).toMatchObject({ value: null, resolved: false });
  });

  it("returns no operands for an analysis with no bindings", () => {
    expect(resolveResearchOperands(analysis(), row({ games: 42 }))).toEqual([]);
  });

  it("uses a unique complete structural match without changing binding identity or value", () => {
    const binding = { operand: "games", sourcePath: "source.*[].games", valueKey: "games", label: "Games" };
    const sourcePaths = ["source.bottom[7].games", "other.bottom[7].games", "source.bottom[7].games_total", "source.bottom[7].nested.games"];
    const item = { ...row({ games: 0 }), sourcePaths };
    expect(resolveResearchOperands(analysis([binding]), item)[0]).toEqual({
      label: "Games", value: 0, sourcePath: binding.sourcePath, rowSourcePath: sourcePaths[0], resolved: true,
    });
    expect(binding.sourcePath).toBe("source.*[].games");
    expect(item.sourcePaths).toEqual(sourcePaths);
  });

  it("retains the schema path when candidates are missing, generic or ambiguous", () => {
    const binding = { operand: "games", sourcePath: "cells[].games", valueKey: "games", label: "Games" };
    for (const sourcePaths of [[], ["other[0].games"], ["cells[].games"], ["cells[0].games", "cells[1].games"]]) {
      const operand = resolveResearchOperands(analysis([binding]), { ...row({ games: 42 }), sourcePaths })[0];
      expect(operand.sourcePath).toBe(binding.sourcePath);
      expect(operand.rowSourcePath).toBeUndefined();
      expect(operand.value).toBe(42);
    }
  });

  it("does not infer paths from expressions, annotations, partial wildcards or selectors", () => {
    for (const sourcePath of ["cells[i].games", "cells[sport=nba].games", "top_*.games", "cells[].games (rounded)", "cells[].games + extra[].games"]) {
      const operand = resolveResearchOperands(analysis([{ operand: "games", sourcePath, valueKey: "games", label: "Games" }]), {
        ...row({ games: 42 }), sourcePaths: ["cells[0].games", "top_nba.games", "extra[0].games"],
      })[0];
      expect(operand.sourcePath).toBe(sourcePath);
      expect(operand.rowSourcePath).toBeUndefined();
    }
  });

  it("keeps unresolved values null and treats duplicate recorded paths as one candidate", () => {
    const operand = resolveResearchOperands(analysis([{ operand: "games", sourcePath: "cells[].games", valueKey: "games", label: "Games" }]), {
      ...row({ games: null }), bindingValues: { games: 42 }, sourcePaths: ["cells[3].games", "cells[3].games"],
    })[0];
    expect(operand).toMatchObject({ value: null, resolved: false, rowSourcePath: "cells[3].games" });
  });

  it("resolves recorded NBA and tennis paths without inventing indices or windows", () => {
    const nba = basketballResearch().find(item => item.id === "nba-variability-imbalance")!;
    const tucker = nba.rows.find(item => item.label === "P.J. Tucker")!;
    const nbaOperands = resolveResearchOperands(nba, tucker);
    expect(nbaOperands.find(item => item.label === "REB shrunk CV")).toMatchObject({
      value: 0.5287, sourcePath: "nba_consistency_profiles.*[].reb_cv_shrunk",
      rowSourcePath: "nba_consistency_profiles.least_consistent_top15[0].reb_cv_shrunk",
    });
    expect(nbaOperands.find(item => item.label === "REB raw league mean CV prior")?.rowSourcePath).toBeUndefined();
    const tennis = getTennisGrassSupportResearch()[0];
    const tennisRow = tennis.rows.find(item => item.label === "Ramkumar Ramanathan (career)")!;
    const operands = resolveResearchOperands(tennis, tennisRow);
    expect(operands.some(item => item.rowSourcePath === "combos.atp_career.grass_adaptability.most_adaptive[0].grass_n")).toBe(true);
    expect(operands.every(item => !item.rowSourcePath || tennisRow.sourcePaths?.includes(item.rowSourcePath))).toBe(true);
  });

  it("retains numeric time-band keys from the published soccer Brier snapshot", () => {
    const brier = buildBrierSkillScoresResearch(brierSource)[0];
    for (const phase of ["0-15", "75-90+"] as const) {
      const soccer = brier.rows.find(item => item.label === `International soccer | ${phase}`)!;
      const operand = resolveResearchOperands(brier, soccer).find(item => item.label === "Model Brier");
      expect(operand).toMatchObject({
        value: brierSource.sports.soccer_intl.grains[phase].brier_model,
        sourcePath: "sports.*.grains.*.brier_model",
        rowSourcePath: `sports.soccer_intl.grains.${phase}.brier_model`,
      });
    }
  });
});
