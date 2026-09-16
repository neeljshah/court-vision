import { describe, expect, it } from "vitest";
import { resolveResearchOperands } from "./researchOperandBindings";
import type { ResearchAnalysis, ResearchRow } from "./researchTypes";

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
});
