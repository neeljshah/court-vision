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
    for (const value of ["34.2", "255.7", "221.5", "10", "6", "29"]) {
      expect(within(selected).getByText(value)).toBeInTheDocument();
    }
    expect(selected).toHaveTextContent("IND");
    expect(selected).toHaveTextContent("HOU");
    expect(screen.getByText(analysis.caveat)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const [dataset, rows] = exportCSV.mock.calls[0];
    const atl = rows.find(row => row.label === "ATL");
    expect(atl?.values).toMatchObject({ high_mean_total: 255.7, low_mean_total: 221.5, high_meetings: 10, low_meetings: 6, opponents: 29 });
    expect(atl?.values.total_range).toBeCloseTo(34.2, 10);
    const csv = table.buildLabCSV(dataset, rows);
    expect(csv).toContain("nba_matchup_grid");
    expect(csv).toContain("IND");
    expect(csv).toContain("HOU");
    expect(csv).toContain("Atlanta Hawks");
    expect(csv).toContain(analysis.caveat);
    expect(csv).toContain(analysis.formula);
    expect(screen.getByRole("link", { name: /Published source JSON/ })).toHaveAttribute("href", "/data/showcase/nba_matchup_grid.json");
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
