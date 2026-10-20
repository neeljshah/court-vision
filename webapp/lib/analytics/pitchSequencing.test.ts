import { describe, expect, it } from "vitest";
import { loadPitchSequencing } from "./pitchSequencing.server";
import { buildPitchSequencing, pitchCell } from "./pitchSequencing";

const fixture = {
  as_of: "2026-07-25", floors: { row_min_n: 200 }, pitch_types: ["FF", "SL"],
  by_class: [{ class: "behind", definition: "published definition", overlapping: false, coverage: 0.9, row_n_from: [10, 4], row_below_floor: [false, true], count_matrix: [[2, 3], [1, 1]], prob_matrix: [[0.2, 0.3], [0.25, 0.25]] }],
};

describe("pitch sequencing data", () => {
  it("keeps each class's published support counts without deriving them from other totals", () => {
    const data = buildPitchSequencing({ ...fixture, n: 999, by_class: [
      { ...fixture.by_class[0], n_transitions_in_class: 100, n_in_matrix: 90 },
      { ...fixture.by_class[0], class: "two_strike", n_transitions_in_class: 50, n_in_matrix: 40 },
    ] });
    expect(data.classes.map(({ transitionsInClass, transitionsInMatrix }) => ({ transitionsInClass, transitionsInMatrix }))).toEqual([
      { transitionsInClass: 100, transitionsInMatrix: 90 },
      { transitionsInClass: 50, transitionsInMatrix: 40 },
    ]);
  });

  it("leaves absent class support counts unpublished even when row and matrix totals exist", () => {
    const data = buildPitchSequencing({ ...fixture, n: 999 });
    expect(data.classes[0]).toMatchObject({ transitionsInClass: null, transitionsInMatrix: null });
  });

  it.each([null, "100", -1, 1.5, NaN, Infinity, -Infinity, Number.MAX_SAFE_INTEGER + 1, true, {}])("rejects invalid support counts: %s", value => {
    const data = buildPitchSequencing({ ...fixture, by_class: [{ ...fixture.by_class[0], n_transitions_in_class: value, n_in_matrix: value }] });
    expect(data.classes[0]).toMatchObject({ transitionsInClass: null, transitionsInMatrix: null });
  });

  it("preserves published zero support counts", () => {
    const data = buildPitchSequencing({ ...fixture, by_class: [{ ...fixture.by_class[0], n_transitions_in_class: 0, n_in_matrix: 0 }] });
    expect(data.classes[0]).toMatchObject({ transitionsInClass: 0, transitionsInMatrix: 0 });
  });

  it("keeps row and column axes aligned to their published pitch types", () => {
    const data = buildPitchSequencing(fixture);
    expect(pitchCell(data, data.classes[0], 0, 1)).toMatchObject({ from: "FF", to: "SL", count: 3, denominator: 10, probability: 0.3 });
  });

  it("marks a masked source row without hiding its published denominator", () => {
    const data = buildPitchSequencing(fixture);
    expect(pitchCell(data, data.classes[0], 1, 0)).toMatchObject({ masked: true, denominator: 4, count: 1 });
  });

  it("retains the published overlap state and does not renormalize a row", () => {
    const data = buildPitchSequencing({ ...fixture, by_class: [{ ...fixture.by_class[0], class: "two_strike", overlapping: true }] });
    expect(data.classes[0].overlapping).toBe(true);
    expect(data.classes[0].probabilityMatrix[0]).toEqual([0.2, 0.3]);
  });

  it("loads the committed browser-safe snapshot without changing its published axes", () => {
    const data = loadPitchSequencing();
    expect(data).toMatchObject({
      pitchTypes: ["FF", "SI", "SL", "CH", "ST", "FC", "CU", "FS"],
      rowMinN: 200,
      asOf: "2026-07-25T11:13:31.944905+00:00",
    });
    expect(data.classes.map(item => item.id)).toEqual(["all", "behind", "even", "ahead", "two_strike", "three_ball"]);
    expect(data.classes.find(item => item.id === "all")).toMatchObject({ transitionsInClass: 512289, transitionsInMatrix: 489035 });
    expect(data.classes.find(item => item.id === "two_strike")).toMatchObject({ transitionsInClass: 206724, transitionsInMatrix: 195987 });
  });
});
