import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getMlbCatcherOozResearch } from "@/lib/analytics/researchMlbCatcherOoz";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analysis = getMlbCatcherOozResearch()[0];
beforeEach(() => window.history.replaceState(null, "", `/analytics/research/${analysis.id}/`));
afterEach(() => vi.restoreAllMocks());

describe("MLB catcher selected-population context", () => {
  it("opens source-ordered measurements with qualification context instead of selected-tail summaries", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByText(analysis.description)).toHaveTextContent("source reports 113 qualifying catcher rows");
    expect(screen.getByText(analysis.description)).toHaveTextContent("minimum: 500 out-of-zone pitches");
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(screen.getByRole("region", { name: "Population comparison notice" })).toHaveTextContent("full qualifying distribution and catcher IDs are unavailable");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("30 matching rows");
  });

  it("keeps both repeated-name rows, their receipts and qualification context in filtered CSV", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Carlos" } });
    expect(screen.getByRole("status")).toHaveTextContent("2 matching rows");
    const buttons = screen.getAllByRole("button", { name: "Inspect Carlos P\u00e9rez" });
    expect(buttons).toHaveLength(2);
    fireEvent.click(buttons[0]);
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    expect(selected).toHaveTextContent("25.3%");
    expect(selected).toHaveTextContent("2,234");
    expect(selected).toHaveTextContent("identity cannot be resolved");
    expect(within(selected).queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const [dataset, rows] = exportCSV.mock.calls[0];
    expect(rows).toHaveLength(2);
    expect(rows.map(row => row.values.out_of_zone_strike_rate)).toEqual([0.253, 0.239]);
    const csv = table.buildLabCSV(dataset, rows);
    for (const value of ["113 qualifying catcher rows", "minimum: 500", "2022-2023", "catcher_ooz.bottom[2]", "catcher_ooz.bottom[12]", "not a framing measure"]) expect(csv).toContain(value);
  });

  it("does not restore pooled distributions or percentiles from a shared chart link", () => {
    window.history.replaceState(null, "", "?view=distribution&row=catcher-ooz-bottom-carlos-p-rez-2");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.queryByRole("region", { name: "Measurement distribution" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
    expect(screen.getByText(/Rankings, distributions, and relative positions require/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("30 matching rows");
  });
});
