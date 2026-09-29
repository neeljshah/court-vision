import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getTennisGrassSupportResearch } from "@/lib/analytics/researchTennisGrassSupport";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analysis = getTennisGrassSupportResearch()[0];
beforeEach(() => window.history.replaceState(null, "", `/analytics/research/${analysis.id}/`));
afterEach(() => vi.restoreAllMocks());

describe("tennis grass support reader", () => {
  it("shows selected rows in source order and distinguishes rate steps from uncertainty", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("20 matching rows");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.getByText(analysis.caveat)).toHaveTextContent("not the grass-minus-overall gap's one-result change");
    expect(screen.getByText(analysis.caveat)).toHaveTextContent("not a confidence interval");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Ramkumar" } });
    fireEvent.click(screen.getByRole("button", { name: "Inspect Ramkumar Ramanathan (career)" }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    expect(within(selected).getByText("6.25 pp")).toBeVisible();
    expect(within(selected).getByText("29.41 pp")).toBeVisible();
    expect(within(selected).getByText("68.75%")).toBeVisible();
    expect(within(selected).getByText("39.34%")).toBeVisible();
    expect(selected).toHaveTextContent("16");
    expect(selected).toHaveTextContent("combos.atp_career.grass_adaptability.most_adaptive[0]");
    expect(screen.queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
  });

  it("keeps overlapping-window rows and all evidence in a filtered CSV", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Christopher Eubanks" } });
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const rows = exportCSV.mock.calls[0][1];
    expect(rows.map(row => row.label)).toEqual(["Christopher Eubanks (career)", "Christopher Eubanks (recent form)"]);
    expect(rows.map(row => row.values.grass_n)).toEqual([26, 22]);
    expect(rows.map(row => row.values.grass_adapt)).toEqual([0.1841, 0.1534]);
    expect(rows[0].values.one_result_step).toBeCloseTo(1 / 26, 12);
    expect(rows[1].values.one_result_step).toBeCloseTo(1 / 22, 12);
    const csv = table.buildLabCSV(analysis, rows);
    for (const value of ["2015-2025", "2023-01-01", "combos.atp_career.grass_adaptability.most_adaptive[3].grass_n", "combos.atp_recent_form.grass_adaptability.most_adaptive[3].grass_n"]) expect(csv).toContain(value);
    expect(analysis.asOf).toBeUndefined();
  });

  it("does not create population ranks from shared chart links", () => {
    window.history.replaceState(null, "", "?view=distribution");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.queryByRole("region", { name: "Measurement distribution" })).not.toBeInTheDocument();
    expect(screen.getByText(/Rankings, distributions, and relative positions require/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("20 matching rows");
  });
});
