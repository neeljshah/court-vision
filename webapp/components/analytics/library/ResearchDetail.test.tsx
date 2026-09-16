import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";

const analysis: ResearchAnalysis = {
  id: "nba-matchup-test", title: "Test matchup analysis", sport: "nba", category: "Matchups", source: "test-source", description: "Historical profile comparison", scope: "Published rows only", caveat: "Descriptive", status: "published", formula: "x / y", interpretation: "Read the measured rows", references: [], novelty: "Derived analysis",
  fields: [{ key: "score", label: "Score", unit: "number" }, { key: "rate", label: "Rate", unit: "percent" }],
  rows: [{ id: "1", label: "Alpha", group: "East", values: { score: 8, rate: 0.5 }, note: "steady", href: "/analytics/players/nba_players/alpha" }, { id: "2", label: "Beta", group: "West", values: { score: null, rate: 0.25 }, note: "missing score" }, { id: "3", label: "Gamma", group: "East", values: { score: 3, rate: 0.75 } }],
};

const brierAnalysis: ResearchAnalysis = {
  ...analysis, id: "brier-skill-score-by-game-phase", title: "Brier skill score by sport and game phase", sport: "all",
  rows: [
    { id: "mlb-all", label: "MLB | all", group: "MLB", values: { score: 8, rate: 0.5 }, sourcePaths: ["sports.mlb.grains.all.brier_model"] },
    { id: "mlb-early", label: "MLB | early", group: "MLB", values: { score: 3, rate: 0.25 }, sourcePaths: ["sports.mlb.grains.early.brier_model"] },
    { id: "soccer-all", label: "International soccer | all", group: "International soccer", values: { score: 7, rate: 0.75 }, sourcePaths: ["sports.soccer_intl.grains.all.brier_model"] },
    { id: "soccer-early", label: "International soccer | 0-15", group: "International soccer", values: { score: 2, rate: 0.4 }, sourcePaths: ["sports.soccer_intl.grains.0-15.brier_model"] },
  ],
};

beforeEach(() => window.history.replaceState(null, "", "/analytics/research/nba-matchup-test/"));
afterEach(() => vi.restoreAllMocks());

describe("ResearchDetail", () => {
  it("separates Brier whole-corpus estimates and requires an explicit all-rows table", () => {
    render(<ResearchDetail analysis={brierAnalysis} related={[]} />);
    expect(screen.getByRole("combobox", { name: "Population" })).toHaveValue("sport=mlb");
    expect(screen.getByRole("status")).toHaveTextContent("1 matching row");
    const population = screen.getByRole("combobox", { name: "Population" });
    expect(within(population).getByRole("option", { name: "MLB" })).toBeInTheDocument();
    expect(within(population).getByRole("option", { name: "International soccer" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Whole-corpus estimates" })).toHaveTextContent("MLB | all");
    fireEvent.change(population, { target: { value: "all" } });
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    expect(screen.getAllByRole("table")).toHaveLength(2);
  });

  it("does not render source context for analyses without recorded sources", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.queryByLabelText("Source context")).not.toBeInTheDocument();
  });

  it("exposes link-sharing updates through a polite live region without a second status role", () => {
    const { container } = render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(container.querySelectorAll('.research-view-actions [aria-live="polite"]')).toHaveLength(1);
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("preserves missing values in the table and supports search, group, and measurement selection", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    expect(screen.getByRole("cell", { name: "Unavailable" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Population" }), { target: { value: "East" } });
    expect(screen.getByRole("status")).toHaveTextContent("2 matching rows");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "gamma" } });
    expect(screen.getByRole("button", { name: /^Inspect Gamma/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Inspect Alpha/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "rate" } });
    fireEvent.click(screen.getByRole("button", { name: /^Inspect Gamma/ }));
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("Rate");
  });

  it("keeps null rows visible after switching from ranked bars to the data table", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("button", { name: /^Inspect Alpha/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    expect(screen.getByRole("button", { name: /^Inspect Beta/ })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Unavailable" })).toBeInTheDocument();
  });
});

describe("ResearchDetail investigation continuity", () => {
  it("uses paired scatter summaries and updates them with the visible search and population", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Scatter plot" }));
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Paired measurement summary" })).toHaveTextContent("2 / 3 rows plotted");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Beta" } });
    expect(screen.getByRole("region", { name: "Paired measurement summary" })).toHaveTextContent("0 / 1 rows plotted");
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "rate" } });
    expect(screen.getByRole("region", { name: "Paired measurement summary" })).toHaveTextContent("1 / 1 rows plotted");
    expect(screen.getByText(/Both axes use the same measurement/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ranked bars" }));
    expect(screen.queryByRole("region", { name: "Paired measurement summary" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Measurement summary" })).toBeInTheDocument();
  });

  it("shows field availability for the selected population and selects a measured field without dropping missing cells", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.click(screen.getByText("Measurement availability"));
    const coverage = screen.getByRole("region", { name: "Measurement availability" });
    expect(within(coverage).getByRole("button", { name: "Use Score" })).toHaveTextContent("2 / 3");
    expect(within(coverage).getByRole("button", { name: "Use Rate" })).toHaveTextContent("3 / 3");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Alpha" } });
    expect(within(coverage).getByRole("button", { name: "Use Score" })).toHaveTextContent("2 / 3");
    expect(coverage).toHaveTextContent("Text search does not change this reference population.");

    fireEvent.change(screen.getByRole("combobox", { name: "Population" }), { target: { value: "West" } });
    expect(within(coverage).getByRole("button", { name: "Use Score" })).toHaveTextContent("0 / 1");
    fireEvent.click(within(coverage).getByRole("button", { name: "Use Rate" }));
    expect(screen.getByRole("combobox", { name: "Measurement" })).toHaveValue("rate");
    expect(within(coverage).getByRole("button", { name: "Use Rate" })).toHaveAttribute("aria-pressed", "true");
    expect(new URLSearchParams(window.location.search).get("metric")).toBe("rate");
    expect(new URLSearchParams(window.location.search).get("group")).toBe("West");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    expect(screen.getByRole("button", { name: "Inspect Beta" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Unavailable" })).toBeInTheDocument();
  });

  it("compares a searched row with its whole selected population and updates the active metric", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Alpha" } });
    fireEvent.click(screen.getByRole("button", { name: /^Inspect Alpha/ }));
    let context = screen.getByRole("region", { name: "Measurement context" });
    expect(context).toHaveTextContent("All published groups");
    expect(within(context).getByText("Reference rows").parentElement).toHaveTextContent("3 rows");
    expect(within(context).getByText("Measured").parentElement).toHaveTextContent("2 / 3");
    expect(within(context).getByText("Missing").parentElement).toHaveTextContent("1 row");
    expect(within(context).getByText("Difference from median").parentElement).toHaveTextContent("+2.5");

    fireEvent.change(screen.getByRole("combobox", { name: "Population" }), { target: { value: "East" } });
    expect(screen.queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Inspect Alpha/ }));
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "rate" } });
    context = screen.getByRole("region", { name: "Measurement context" });
    expect(context).toHaveTextContent("East");
    expect(within(context).getByText("Measured").parentElement).toHaveTextContent("2 / 2");
    expect(within(context).getByText("Median").parentElement).toHaveTextContent("62.5%");
    expect(within(context).getByText("Difference from median").parentElement).toHaveTextContent("-12.5 pp");
  });

  it("restores the distribution view and recalculates summaries after filtering", () => {
    window.history.replaceState(null, "", "?metric=rate&view=distribution&q=Alpha");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("button", { name: /^Distribution$/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", { name: "Measurement summary" })).toHaveTextContent("50%");
    expect(screen.getByRole("region", { name: "Measurement distribution" })).toHaveTextContent("Every measured row has the same value: 50%");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Beta" } });
    expect(screen.getByRole("region", { name: "Measurement summary" })).toHaveTextContent("25%");
    expect(new URLSearchParams(window.location.search).get("view")).toBe("distribution");
  });

  it("restores a shared investigation and clears stale selection when filtering", () => {
    window.history.replaceState(null, "", "?metric=rate&y=score&group=East&q=gamma&order=asc&view=scatter&row=3&utm_source=shared");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("combobox", { name: /^Measurement$/ })).toHaveValue("rate");
    expect(screen.getByRole("combobox", { name: "Vertical measurement" })).toHaveValue("score");
    expect(screen.getByRole("combobox", { name: "Order" })).toHaveValue("asc");
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveFocus();
    expect(screen.getByRole("status")).toHaveTextContent("1 matching row; 1 contains rate");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "alpha" } });
    const p = new URLSearchParams(window.location.search);
    expect(p.get("q")).toBe("alpha");
    expect(p.get("row")).toBeNull();
    expect(p.get("utm_source")).toBe("shared");
    expect(screen.queryByRole("region", { name: "Selected measurement" })).not.toBeInTheDocument();
  });

  it("rejects malformed fields and restores browser history without stale controls", () => {
    window.history.replaceState(null, "", "?metric=bad&y=bad&group=bad&view=bad&row=unknown");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("combobox", { name: "Measurement" })).toHaveValue("score");
    expect(window.location.search).toBe("");
    act(() => {
      window.history.pushState(null, "", "?metric=rate&view=table&group=West&row=2");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByRole("combobox", { name: "Measurement" })).toHaveValue("rate");
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("Beta");
    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(screen.getByRole("status")).toHaveTextContent("3 matching rows");
    expect(window.location.search).toBe("");
  });

  it("exports complete filtered rows from bars and tables, retaining null measurements", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    expect(exportCSV.mock.calls[0][1].map(r => r.id)).toEqual(["1", "3", "2"]);
    expect(exportCSV.mock.calls[0][1][2].values.score).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    expect(exportCSV.mock.calls[1][1]).toEqual(exportCSV.mock.calls[0][1]);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "absent" } });
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeDisabled();
  });

  it("returns keyboard focus to the inspected row on Escape", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    const button = screen.getByRole("button", { name: /^Inspect Alpha/ });
    button.focus(); fireEvent.click(button);
    const details = screen.getByRole("region", { name: "Selected measurement" });
    expect(details).toHaveFocus();
    fireEvent.keyDown(details, { key: "Escape" });
    expect(button).toHaveFocus();
    expect(screen.queryByRole("region", { name: "Selected measurement" })).not.toBeInTheDocument();
  });

  it("offers the selected row's entity card without changing Escape focus return", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    const button = screen.getByRole("button", { name: /^Inspect Alpha/ });
    button.focus(); fireEvent.click(button);
    expect(screen.getByRole("link", { name: "Open entity card" })).toHaveAttribute("href", "/analytics/players/nba_players/alpha");
    fireEvent.keyDown(screen.getByRole("region", { name: "Selected measurement" }), { key: "Escape" });
    expect(button).toHaveFocus();
  });
});
