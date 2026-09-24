import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import ResearchDetail from "./ResearchDetail";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";

const analysis: ResearchAnalysis = {
  id: "nba-focus-test", title: "Published measurements", sport: "nba", category: "Measurements",
  source: "test-source", description: "Historical measurements", scope: "Published rows only",
  caveat: "Descriptive", status: "published", formula: "Published values",
  interpretation: "Inspect the source records", references: [], novelty: "Derived analysis",
  fields: [{ key: "score", label: "Score", unit: "number" }, { key: "rate", label: "Rate", unit: "percent" }],
  rows: [{ id: "alpha", label: "Alpha", group: "NBA", values: { score: 8, rate: 0.5 } }],
};

beforeEach(() => window.history.replaceState(null, "", "/analytics/research/nba-focus-test/?view=table"));

describe("ResearchDetail focus recovery", () => {
  it.each(["Escape", "close button"])("returns a shared-link inspector to row search using %s", method => {
    window.history.replaceState(null, "", "?view=table&row=alpha&q=Alpha&utm_source=shared");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    const details = screen.getByRole("region", { name: "Selected measurement" });
    expect(details).toHaveFocus();
    if (method === "Escape") fireEvent.keyDown(details, { key: "Escape" });
    else fireEvent.click(screen.getByRole("button", { name: "Close measurement" }));
    expect(screen.queryByRole("region", { name: "Selected measurement" })).not.toBeInTheDocument();
    const search = screen.getByRole("textbox", { name: "Search analysis rows" });
    expect(search).toHaveFocus();
    expect(search).toHaveValue("Alpha");
    const params = new URLSearchParams(window.location.search);
    expect(params.has("row")).toBe(false);
    expect(params.get("utm_source")).toBe("shared");
  });

  it("keeps focus on the original row when its trigger remains available", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    const button = screen.getByRole("button", { name: "Inspect Alpha" });
    button.focus();
    fireEvent.click(button);
    fireEvent.keyDown(screen.getByRole("region", { name: "Selected measurement" }), { key: "Escape" });
    expect(button).toHaveFocus();
  });

  it("returns to row search when changing the measurement replaces the original table trigger", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    const button = screen.getByRole("button", { name: "Inspect Alpha" });
    button.focus();
    fireEvent.click(button);
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "rate" } });
    expect(button.isConnected).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Close measurement" }));
    expect(screen.getByRole("textbox", { name: "Search analysis rows" })).toHaveFocus();
    expect(screen.getByRole("combobox", { name: "Measurement" })).toHaveValue("rate");
  });
});
