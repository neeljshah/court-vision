import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ResearchDetail from "./ResearchDetail";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";

const analysis: ResearchAnalysis = {
  id: "nba-matchup-test", title: "Test matchup analysis", sport: "nba", category: "Matchups", source: "test-source", description: "Historical profile comparison", scope: "Published rows only", caveat: "Descriptive", status: "published", formula: "x / y", interpretation: "Read the measured rows", references: [], novelty: "Derived analysis",
  fields: [{ key: "score", label: "Score", unit: "number" }, { key: "rate", label: "Rate", unit: "percent" }],
  rows: [{ id: "1", label: "Alpha", group: "East", values: { score: 8, rate: 0.5 }, note: "steady" }, { id: "2", label: "Beta", group: "West", values: { score: null, rate: 0.25 }, note: "missing score" }, { id: "3", label: "Gamma", group: "East", values: { score: 3, rate: 0.75 } }],
};

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
