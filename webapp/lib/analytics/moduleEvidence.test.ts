import { describe, expect, it } from "vitest";
import { classifyModuleEvidence } from "./moduleEvidence";
const research = [{ id: "surface-support", title: "Surface support", source: "tennis_surface_transfer" }] as never;
describe("module evidence", () => {
  it("uses an artifact absence over a conflicting manifest status", () => {
    const result = classifyModuleEvidence("aging_curve_lite", "ok", { status: "not_buildable", why: "Age-labeled seasons are absent.", age_source_found: null }, research);
    expect(result.availability).toBe("unavailable");
    expect(result.headline).toContain("Age-labeled seasons are absent");
  });
  it("names explicit missing inputs", () => {
    const result = classifyModuleEvidence("x", "ok", { status: "not_buildable", age_source_found: false }, research);
    expect(result.missingInputs).toEqual(["Age Source Found"]);
  });
  it("preserves partial per-population coverage", () => {
    const result = classifyModuleEvidence("xsport_structure", "partial", { sports: { nba: { status: "ok", n_games_total: 1593, n_buckets_usable: 77 }, tennis: { status: "not_buildable", reason: "no map" } } }, research);
    expect(result.availability).toBe("partial");
    expect(result.coverage).toEqual(expect.arrayContaining([expect.objectContaining({ population: "NBA", nGamesTotal: 1593 }), expect.objectContaining({ population: "TENNIS", reason: "no map" })]));
  });
  it("finds interactive analysis destinations by source module", () => {
    expect(classifyModuleEvidence("tennis_surface_transfer", "ok", {}, research).analyses).toEqual([{ id: "surface-support", title: "Surface support" }]);
  });
});
