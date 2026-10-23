import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ResearchDetail from "./ResearchDetail";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";

const analysis: ResearchAnalysis = {
  id: "pagination", title: "Pagination fixture", sport: "nba", category: "Fixture", source: "fixture",
  description: "Fixture", scope: "Fixture", caveat: "Fixture", status: "published",
  formula: "Fixture", interpretation: "Fixture", references: [], novelty: "Derived analysis",
  fields: [{ key: "value", label: "Value", unit: "number" }, { key: "other", label: "Other", unit: "number" }],
  rows: Array.from({ length: 25 }, (_, i) => ({
    id: String(i), label: `Team ${String(i).padStart(2, "0")}`, group: i < 13 ? "East" : "West",
    values: { value: i === 24 ? null : 25 - i, other: i },
  })),
};
const params = () => new URLSearchParams(window.location.search);
const open = (search: string, a = analysis) => {
  window.history.replaceState(null, "", `/analytics/research/pagination/?${search}`);
  return render(<ResearchDetail analysis={a} related={[]} />);
};
const firstRow = () => within(screen.getByRole("table")).getAllByRole("row")[1];

beforeEach(() => window.history.replaceState(null, "", "/analytics/research/pagination/"));
afterEach(() => vi.restoreAllMocks());

describe("shared research table pages", () => {
  it("copies page two and reopens the same rows and inspector", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const rendered = open("view=table&utm_source=shared#measurements");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(firstRow()).toHaveTextContent("Team 12");
    fireEvent.click(screen.getByRole("button", { name: "Inspect Team 12" }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy view link" })));
    const copied = new URL(writeText.mock.calls[0][0]);
    expect(copied.searchParams.get("page")).toBe("2");
    expect(copied.searchParams.get("row")).toBe("12");
    expect(copied.searchParams.get("utm_source")).toBe("shared");
    expect(copied.hash).toBe("#measurements");
    rendered.unmount();
    open(copied.search.slice(1) + copied.hash);
    expect(screen.getByText("Page 2 / 3")).toBeInTheDocument();
    expect(firstRow()).toHaveTextContent("Team 12");
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("Team 12");
    fireEvent.click(screen.getByRole("button", { name: "Close measurement" }));
    expect(params().get("page")).toBe("2");
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(params().has("page")).toBe(false);
    expect(window.location.hash).toBe("#measurements");
  });

  it("restores page changes from browser navigation with the requested filters", () => {
    open("view=table");
    act(() => {
      window.history.pushState(null, "", "?view=table&page=2&group=East&order=asc&utm_source=history#rows");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByText("Page 2 / 2")).toBeInTheDocument();
    expect(firstRow()).toHaveTextContent("Team 00");
    expect(params().get("page")).toBe("2");
    expect(params().get("utm_source")).toBe("history");
    expect(window.location.hash).toBe("#rows");
    act(() => {
      window.history.replaceState(null, "", "?view=table");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByText("Page 1 / 3")).toBeInTheDocument();
    expect(firstRow()).toHaveTextContent("Team 00");
  });

  it.each(["0", "-1", "1.5", "2e0", "Infinity", "NaN", "9007199254740992", "02", " 2", "2oops", ""])("normalizes invalid page %j", page => {
    open(`view=table&page=${encodeURIComponent(page)}&utm_source=shared#rows`);
    expect(screen.getByText("Page 1 / 3")).toBeInTheDocument();
    expect(params().has("page")).toBe(false);
    expect(params().get("utm_source")).toBe("shared");
    expect(window.location.hash).toBe("#rows");
  });

  it("clamps to the last matching page and counts missing measurements", () => {
    open("view=table&page=999");
    expect(screen.getByText("Page 3 / 3")).toBeInTheDocument();
    expect(firstRow()).toHaveTextContent("Team 24");
    expect(firstRow()).toHaveTextContent("Unavailable");
    expect(params().get("page")).toBe("3");
  });

  it("clamps against URL search and group together", () => {
    open("view=table&page=3&group=East&q=Team");
    expect(screen.getByText("Page 2 / 2")).toBeInTheDocument();
    expect(firstRow()).toHaveTextContent("Team 12");
    expect(params().get("page")).toBe("2");
  });

  it("normalizes to page one when no rows match", () => {
    open("view=table&page=2&q=no-match");
    expect(screen.getByText("No published rows match this search and population.")).toBeInTheDocument();
    expect(params().has("page")).toBe(false);
  });

  it.each([["Measurement", "other"], ["Order", "asc"], ["Population", "East"]])("resets a changed %s to page one", (name, value) => {
    open("view=table&page=2");
    expect(screen.getByText("Page 2 / 3")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: new RegExp(`^${name}$`) }), { target: { value } });
    expect(screen.getByText(/^Page 1 \/ /)).toBeInTheDocument();
    expect(params().has("page")).toBe(false);
  });

  it("resets changed search, chart and reset controls but keeps an unchanged table choice", () => {
    const rendered = open("view=table&page=2");
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    expect(params().get("page")).toBe("2");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Team" } });
    expect(params().has("page")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Ranked bars" }));
    expect(params().has("page")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    expect(screen.getByText("Page 1 / 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(params().has("page")).toBe(false);
    rendered.unmount();
  });

  it("uses the selected sport's component rows without counting whole-corpus estimates", () => {
    const phases: ResearchAnalysis = { ...analysis, sport: "all", rows: [
      ...analysis.rows.slice(0, 12).map(row => ({ ...row, group: "NBA", sourcePaths: ["sports.nba.grains.early.brier_model"] })),
      { id: "all", label: "NBA aggregate", group: "NBA", values: { value: 0.2 }, sourcePaths: ["sports.nba.grains.all.brier_model"] },
      ...analysis.rows.map(row => ({ ...row, id: `mlb-${row.id}`, label: `MLB ${row.id}`, group: "MLB", sourcePaths: ["sports.mlb.grains.early.brier_model"] })),
    ] };
    open("view=table&population=sport%3Dnba&page=2", phases);
    expect(screen.getAllByText("Page 1 / 1")).toHaveLength(2);
    expect(params().has("page")).toBe(false);
    fireEvent.change(screen.getByRole("combobox", { name: "Population" }), { target: { value: "sport=mlb" } });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(params().get("page")).toBe("2");
    fireEvent.change(screen.getByRole("combobox", { name: "Population" }), { target: { value: "sport=nba" } });
    expect(params().has("page")).toBe(false);
  });
});
