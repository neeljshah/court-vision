import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getSoccerScoringResearch } from "@/lib/analytics/researchSoccerScoring";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analysis = getSoccerScoringResearch();
beforeEach(() => window.history.replaceState(null, "", `/analytics/research/${analysis.id}/`));
afterEach(() => vi.restoreAllMocks());

describe("Soccer attack and defense investigation", () => {
  it("connects a team's signed balance to its scoring operands and CSV provenance", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Order" })).toHaveTextContent("Published source order");
    expect(screen.getByRole("region", { name: "Population comparison notice" })).toHaveTextContent(analysis.populationDefinition?.reason || "");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    const sourceContext = screen.getByRole("region", { name: "Source context" });
    expect(sourceContext).toHaveTextContent("Row window: Goal difference per game: exactly 10 strictly prior all-venue matches");
    expect(sourceContext).toHaveTextContent("Goals scored per game: exactly 10 strictly prior all-venue matches");
    expect(sourceContext).toHaveTextContent("Goals conceded per game: exactly 10 strictly prior all-venue matches");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Bayern Munich" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 matching row");
    fireEvent.click(screen.getByRole("button", { name: "Inspect Bayern Munich" }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    expect(within(selected).queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
    for (const [label, value] of [["Goal difference per game", "1.8"], ["Goals scored per game", "3.2"], ["Goals conceded per game", "1.4"]]) {
      expect(within(within(selected).getByText(label).parentElement!).getByText(value)).toBeVisible();
    }
    const provenance = within(selected).getByRole("region", { name: "Calculation inputs" });
    expect(provenance).toHaveTextContent("3.2");
    expect(provenance).toHaveTextContent("1.4");
    expect(provenance).not.toHaveTextContent("not published for this row");
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const [dataset, rows] = exportCSV.mock.calls[0];
    expect(rows).toHaveLength(1);
    expect(rows[0].values).toEqual({ gd_l10: 1.8, gf_l10: 3.2, ga_l10: 1.4 });
    const csv = table.buildLabCSV(dataset, rows);
    for (const text of ["Bayern Munich", "atlas_soccer_manifest", "2026-07-18T17:21:08.108324+00:00", "Row windows (JSON)", analysis.caveat]) expect(csv).toContain(text);
  });

  it("restores a shared negative-balance table and its selected measurement", () => {
    window.history.replaceState(null, "", "?q=Ajaccio&view=table&metric=ga_l10&utm_source=shared");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("combobox", { name: "Measurement" })).toHaveValue("ga_l10");
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    const measurements = screen.getByRole("region", { name: "Scrollable measurements" });
    for (const value of ["-2.4", "0.2", "2.6"]) expect(within(measurements).getByText(value)).toBeVisible();
    expect(new URLSearchParams(window.location.search).get("utm_source")).toBe("shared");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "no matching soccer team" } });
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeDisabled();
    expect(screen.getByText("No published rows match this search and population.")).toBeVisible();
  });

  it("does not restore a pooled chart or relative position from a forged URL", () => {
    window.history.replaceState(null, "", "?population=sport%3Dsoccer&view=distribution&row=soccer-scoring-bayern-munich");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("region", { name: "Population comparison notice" })).toHaveTextContent("comparable population cannot be verified");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Measurement distribution" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    expect(screen.getByRole("region", { name: "Scrollable measurements" })).toBeVisible();
  });
});
