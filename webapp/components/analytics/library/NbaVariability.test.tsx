import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { basketballResearch } from "@/lib/analytics/researchBasketball";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analysis = basketballResearch().find(item => item.id === "nba-variability-imbalance")!;
beforeEach(() => window.history.replaceState(null, "", `/analytics/research/${analysis.id}/`));
afterEach(() => vi.restoreAllMocks());

describe("NBA variability reader", () => {
  it("shows selected source rows with signed gaps and their published priors", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("30 matching rows");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Luka" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "pts_cv_vs_prior" } });
    fireEvent.click(screen.getByRole("button", { name: "Inspect Luka Doncic" }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    expect(selected).toHaveTextContent("-0.2443");
    expect(selected).toHaveTextContent("-0.1992");
    expect(selected).toHaveTextContent("-0.385");
    const inputs = within(selected).getByRole("region", { name: "Calculation inputs" });
    expect(inputs).toHaveTextContent("0.5242");
    expect(inputs).toHaveTextContent("0.5561");
    expect(inputs).toHaveTextContent("0.7825");
    expect(inputs).toHaveTextContent("90.2%");
    expect(inputs).toHaveTextContent("nba_consistency_profiles.most_consistent_top15[0].pts_cv_shrunk");
    expect(inputs).toHaveTextContent("source K = 20 games");
    expect(screen.getByText(analysis.caveat)).toHaveTextContent("not an independent comparison sample");
    expect(screen.queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
  });

  it("exports raw CV-unit gaps with priors, dates, source paths and subset limits", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "P.J. Tucker" } });
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const rows = exportCSV.mock.calls[0][1];
    expect(rows).toHaveLength(1);
    expect(rows[0].values.reb_cv_vs_prior).toBeCloseTo(-0.0274, 8);
    expect(rows[0].values.pts_cv_vs_prior).toBeCloseTo(0.3620, 8);
    expect(rows[0].values.shrink_weight).toBe(0.565);
    expect(rows[0].bindingValues?.reb_prior).toBe(0.5561);
    const csv = table.buildLabCSV(analysis, rows);
    for (const value of ["2026-04-12", "2023-24, 2024-25, 2025-26", "579", "selected extremes", "least_consistent_top15[0].reb_cv_shrunk", "methodology.league_mean_cv_raw.reb"]) expect(csv).toContain(value);
    expect(analysis.interpretation).toContain("dimensionless CV units");
  });

  it("rejects a shared distribution view for the selected extremes", () => {
    window.history.replaceState(null, "", "?view=distribution");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.queryByRole("region", { name: "Measurement distribution" })).not.toBeInTheDocument();
    expect(screen.getByText(/Rankings, distributions, and relative positions require/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("30 matching rows");
  });
});
