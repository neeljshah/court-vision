import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as helpers from "@/lib/analytics/labHelpers";
import { novelDatasets } from "@/lib/analytics/labNovel";
import MeasurementLab from "./MeasurementLab";
import * as table from "./LabTable";

const source = helpers.snapshot<{ as_of: { estimator_a: string; estimator_b: string } }>("novel_load_bearing_index");
const published = novelDatasets().find(item => item.id === "load-bearing")!;
beforeEach(() => window.history.replaceState(null, "", "/analytics/lab/?dataset=load-bearing&mode=table"));
afterEach(() => vi.restoreAllMocks());

describe("load-bearing estimator periods", () => {
  it("shows each exact published period and carries both into the published window", () => {
    render(<MeasurementLab data={{ datasets: [published], novel: [] }} />);
    const scope = screen.getByText(published.scope);
    expect(scope).toHaveTextContent(`Estimator A period: ${source.as_of.estimator_a}`);
    expect(scope).toHaveTextContent(`Estimator B period: ${source.as_of.estimator_b}`);
    expect(screen.getByRole("combobox", { name: "Rank order" })).not.toBeDisabled();
    expect(screen.getByRole("region", { name: "Measurement summary" })).toBeInTheDocument();
    expect(published.rows.every(row => row.definition?.observationWindow === `Estimator A: ${source.as_of.estimator_a}; Estimator B: ${source.as_of.estimator_b}`)).toBe(true);
    expect(published.rows.every(row => row.definition?.sport === undefined)).toBe(true);
    expect(screen.getByText("Sport").nextElementSibling).toHaveTextContent("Not published");
  });

  it("preserves both periods when exporting a filtered team and keeps its measurements", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<MeasurementLab data={{ datasets: [published], novel: [] }} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "Aaron Gordon" } });
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    const [dataset, rows] = exportCSV.mock.calls[0];
    expect(rows).toEqual(published.rows.filter(row => row.label === "DEN"));
    expect(rows).toHaveLength(1);
    expect(rows[0].values).toEqual({ delta_winprob: 0.5822, delta_win_rate: 0.1818, n_active: 36, n_missed: 44 });
    const csv = table.buildLabCSV(dataset, rows);
    expect(csv).toContain(`Estimator A period: ${source.as_of.estimator_a}`);
    expect(csv).toContain(`Estimator B period: ${source.as_of.estimator_b}`);
    expect(csv).toContain("Same player: no.");
  });

  it.each([
    { periods: undefined, a: "not published", b: "not published" },
    { periods: { estimator_a: "   ", estimator_b: source.as_of.estimator_b }, a: "not published", b: source.as_of.estimator_b },
    { periods: { estimator_a: source.as_of.estimator_a, estimator_b: "" }, a: source.as_of.estimator_a, b: "not published" },
  ])("marks unavailable periods independently: $a / $b", ({ periods, a, b }) => {
    const originalSnapshot = helpers.snapshot;
    vi.spyOn(helpers, "snapshot").mockImplementation(<T,>(id: string): T => id === "novel_load_bearing_index"
      ? { ...source, as_of: periods } as T : originalSnapshot<T>(id));
    const dataset = novelDatasets().find(item => item.id === "load-bearing")!;
    expect(dataset.scope).toContain(`Estimator A period: ${a}.`);
    expect(dataset.scope).toContain(`Estimator B period: ${b}.`);
    expect(dataset.rows.map(row => ({ ...row, definition: undefined }))).toEqual(published.rows.map(row => ({ ...row, definition: undefined })));
    expect(dataset.rows.every(row => row.definition?.observationWindow === undefined)).toBe(true);
    expect(table.buildLabCSV(dataset, dataset.rows)).toContain(dataset.scope);
  });
});
