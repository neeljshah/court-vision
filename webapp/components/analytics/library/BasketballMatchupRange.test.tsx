import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getBasketballMatchupRangeResearch } from "@/lib/analytics/researchBasketballMatchupRange";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analysis = getBasketballMatchupRangeResearch()[0];
beforeEach(() => window.history.replaceState(null, "", "/analytics/research/nba-opponent-total-range/"));
afterEach(() => vi.restoreAllMocks());

describe("Published NBA opponent mean-total investigation", () => {
  it("keeps the scoring endpoints and meeting supports visible and in the CSV", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "ATL" } });
    fireEvent.click(screen.getByRole("button", { name: /^Inspect ATL:/ }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    for (const [label, value] of [
      ["High-low mean-total range", "34.2"],
      ["Highest opponent mean total", "255.7"],
      ["Lowest opponent mean total", "221.5"],
      ["Selected high-end pair meetings", "10"],
      ["Selected low-end pair meetings", "6"],
      ["Opponents represented", "29"],
      ["Meeting-weighted mean combined total", "236.98"],
      ["Between-opponent mean-total SD", "9.1"],
      ["Team-meetings across included pairings", "239"],
    ]) {
      const term = within(selected).getByText(label, { selector: "dt" });
      expect(within(term.parentElement!).getByText(value, { selector: "dd" })).toBeInTheDocument();
    }
    expect(selected).toHaveTextContent("IND");
    expect(selected).toHaveTextContent("HOU");
    expect(screen.getByText(analysis.caveat)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const [dataset, rows] = exportCSV.mock.calls[0];
    const atl = rows.find(row => row.label === "ATL");
    expect(atl?.values).toMatchObject({ high_mean_total: 255.7, low_mean_total: 221.5, high_meetings: 10, low_meetings: 6, opponents: 29 });
    expect(atl?.values.total_range).toBeCloseTo(34.2, 10);
    expect(atl?.values.meeting_weighted_mean_total).toBeCloseTo(236.98301255230132, 10);
    expect(atl?.values.between_opponent_mean_total_sd).toBeCloseTo(9.100866994186187, 10);
    expect(atl?.values.meetings_across_pairings).toBe(239);
    const csv = table.buildLabCSV(dataset, rows);
    expect(csv).toContain("Meeting-weighted mean combined total (number; raw value)");
    expect(csv).toContain("Between-opponent mean-total SD (number; raw value)");
    expect(csv).toContain("Team-meetings across included pairings (number; raw value)");
    expect(csv).toContain("nba_matchup_grid");
    expect(csv).toContain("IND");
    expect(csv).toContain("HOU");
    expect(csv).toContain("Atlanta Hawks");
    expect(csv).toContain(analysis.caveat);
    expect(csv).toContain(analysis.formula);
    expect(screen.getByRole("link", { name: /Published source JSON/ })).toHaveAttribute("href", "/data/showcase/nba_matchup_grid.json");
  });

  it("lets readers select the pair-mean dispersion, filter a team, and inspect its support", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement", exact: true }), { target: { value: "between_opponent_mean_total_sd" } });
    expect(screen.getByRole("status")).toHaveTextContent("30 matching rows; 30 contain between-opponent mean-total sd.");
    expect(new URLSearchParams(window.location.search).get("metric")).toBe("between_opponent_mean_total_sd");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Atlanta Hawks" } });
    fireEvent.click(screen.getByRole("button", { name: "Inspect ATL: 9.1", exact: true }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    expect(selected).toHaveTextContent("Team-meetings across included pairings239");
    fireEvent.click(screen.getByRole("button", { name: "Data table", exact: true }));
    expect(screen.getByRole("columnheader", { name: "Between-opponent mean-total SD", exact: true })).toBeVisible();
    expect(screen.getByRole("columnheader", { name: "Team-meetings across included pairings", exact: true })).toBeVisible();
  });

  it("finds published city and team names while preserving multi-word search", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    const search = screen.getByRole("textbox", { name: "Search analysis rows" });
    for (const [query, team] of [["Atlanta", "ATL"], ["Hawks", "ATL"], ["aTlAnTa hAwKs", "ATL"], ["New York Knicks", "NYK"], ["LA Clippers", "LAC"]]) {
      fireEvent.change(search, { target: { value: query } });
      expect(screen.getByRole("status")).toHaveTextContent("1 matching row;");
      expect(screen.getByRole("button", { name: new RegExp(`^Inspect ${team}:`) })).toBeInTheDocument();
    }
    fireEvent.change(search, { target: { value: "Atlanta Lakers" } });
    expect(screen.getByRole("status")).toHaveTextContent("0 matching rows;");
    expect(screen.getByText("No published rows match this search and population.")).toBeVisible();
  });
});
