import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";

const analysis: ResearchAnalysis = {
  id: "nba-matchup-test", title: "Test matchup analysis", sport: "nba", category: "Matchups", source: "test-source", description: "Historical profile comparison", scope: "Published rows only", caveat: "Descriptive", status: "published", formula: "x / y", interpretation: "Read the measured rows", references: [], novelty: "Derived analysis",
  fields: [{ key: "score", label: "Score", unit: "number" }, { key: "rate", label: "Rate", unit: "percent" }],
  rows: [{ id: "1", label: "Alpha", group: "East", values: { score: 8, rate: 0.5 }, note: "steady" }, { id: "2", label: "Beta", group: "West", values: { score: null, rate: 0.25 }, note: "missing score" }, { id: "3", label: "Gamma", group: "East", values: { score: 3, rate: 0.75 } }],
};

beforeEach(() => window.history.replaceState(null, "", "/analytics/research/nba-matchup-test/"));
afterEach(() => vi.restoreAllMocks());

describe("ResearchDetail", () => {
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
  it("restores the distribution view and recalculates summaries after filtering", () => {
    window.history.replaceState(null, "", "?metric=rate&view=distribution&q=Alpha");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("button", { name: "Distribution", exact: true })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", { name: "Measurement summary" })).toHaveTextContent("50%");
    expect(screen.getByRole("region", { name: "Measurement distribution" })).toHaveTextContent("Every measured row has the same value: 50%");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Beta" } });
    expect(screen.getByRole("region", { name: "Measurement summary" })).toHaveTextContent("25%");
    expect(new URLSearchParams(window.location.search).get("view")).toBe("distribution");
  });

  it("restores a shared investigation and clears stale selection when filtering", () => {
    window.history.replaceState(null, "", "?metric=rate&y=score&group=East&q=gamma&order=asc&view=scatter&row=3&utm_source=shared");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("combobox", { name: "Measurement", exact: true })).toHaveValue("rate");
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
});
