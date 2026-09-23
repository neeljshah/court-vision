import { describe, expect, it } from "vitest";
import tennisShowcase from "../../public/data/showcase/tennis_showcase.json";
import { buildTennisSurfaceFolds } from "./tennisSurfaceFolds";

describe("buildTennisSurfaceFolds", () => {
  it("preserves the six published rows, tour boundaries, order, and provenance", () => {
    const groups = buildTennisSurfaceFolds(tennisShowcase.ingame_surface_context.tours);

    expect(groups.map(group => group.tour)).toEqual(["atp", "wta"]);
    expect(groups[0].rows.map(row => [row.fold, row.testStates, row.delta])).toEqual([
      [0, 8780, .000096],
      [1, 8780, .000042],
      [2, 8780, .000224],
    ]);
    expect(groups[1].rows.map(row => [row.fold, row.testStates, row.delta])).toEqual([
      [0, 2646, .001652],
      [1, 2645, .002381],
      [2, 2646, .003442],
    ]);
    expect(groups[0].rows[0]).toMatchObject({
      sourceIndex: 0,
      blindBrier: .166648,
      surfaceBrier: .166744,
      sourcePath: "ingame_surface_context.tours.atp.n_folds[0]",
    });
    expect(groups[1].rows[2].sourcePath).toBe("ingame_surface_context.tours.wta.n_folds[2]");
  });

  it("fails invalid scalars closed while retaining valid zero values", () => {
    const [atp] = buildTennisSurfaceFolds({ atp: { n_folds: [
      { fold: 0, n_test: 0, brier_h0: 0, brier_h1: 0 },
      { fold: -1, n_test: -3, brier_h0: -1, brier_h1: 2 },
      { fold: 1.5, n_test: 2.5, brier_h0: Infinity, brier_h1: NaN },
      { fold: Number.MAX_SAFE_INTEGER + 1, n_test: Number.MAX_SAFE_INTEGER + 1 },
    ] } });

    expect(atp.rows[0]).toMatchObject({ fold: 0, testStates: null, blindBrier: 0, surfaceBrier: 0, delta: 0 });
    expect(atp.rows.slice(1).every(row => row.fold === null && row.testStates === null)).toBe(true);
    expect(atp.rows.slice(1).every(row => row.blindBrier === null && row.surfaceBrier === null && row.delta === null)).toBe(true);
  });

  it("derives a same-row delta without fabricating missing support", () => {
    const [atp] = buildTennisSurfaceFolds({ atp: { n_folds: [
      { fold: 4, brier_h0: .2, brier_h1: .25 },
    ] } });

    expect(atp.rows[0]).toMatchObject({ testStates: null, blindBrier: .2, surfaceBrier: .25, delta: .05 });
  });

  it("keeps malformed placeholders and duplicate fold labels at their source indices", () => {
    const [atp] = buildTennisSurfaceFolds({ atp: { n_folds: [
      { fold: 2, n_test: 10, brier_h0: .1, brier_h1: .2 },
      null,
      { fold: 2, n_test: 12, brier_h0: .3, brier_h1: .3 },
    ] } });

    expect(atp.rows).toHaveLength(3);
    expect(atp.rows.map(row => [row.sourceIndex, row.fold])).toEqual([[0, 2], [1, null], [2, 2]]);
    expect(atp.rows[1]).toMatchObject({
      testStates: null,
      blindBrier: null,
      surfaceBrier: null,
      delta: null,
      sourcePath: "ingame_surface_context.tours.atp.n_folds[1]",
    });
  });

  it("returns empty groups for missing tour blocks or non-array folds", () => {
    expect(buildTennisSurfaceFolds(null)).toEqual([
      { tour: "atp", rows: [] },
      { tour: "wta", rows: [] },
    ]);
    expect(buildTennisSurfaceFolds({ atp: { n_folds: {} } })).toEqual([
      { tour: "atp", rows: [] },
      { tour: "wta", rows: [] },
    ]);
  });
});
