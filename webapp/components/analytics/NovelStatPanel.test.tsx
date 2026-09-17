import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { NovelStatPanel, windowText } from "./NovelStatPanel";

describe("NovelStatPanel", () => {
  it("renders a results-shaped artifact as a table", () => {
    render(<NovelStatPanel stat={{ stat_name: "Line Half Life", abbrev: "LHL", headline: "Half of the motion is done early.", results: [{ sport: "nba", n_move_pairs: 1200, half_life_label: "6h" }] }} />);
    expect(screen.getByText("Half of the motion is done early.")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "n move pairs" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "1200" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Published results 1 (scrollable table)" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByText("Scroll horizontally for all columns")).toBeInTheDocument();
  });

  it("renders no results table for a panels-shaped artifact", () => {
    // novel_rest_asymmetry publishes `panels`, which this renderer has no schema for;
    // its module page mounts RestAsymmetryPanel instead of widening this component.
    render(<NovelStatPanel stat={{ stat_name: "Rest Asymmetry", panels: { rest_differential: { n_games: 4793, cells: [{ cell: "equal", n_games: 2639 }] } } }} />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("The results")).not.toBeInTheDocument();
  });

  it("reads an observation window without inventing one", () => {
    expect(windowText({ start: "2025-10-01", end: "2026-04-12", days: 194 })).toBe("observed 2025-10-01 to 2026-04-12 (194 days)");
    expect(windowText({ start: "2025-10-01" })).toBe("");
    expect(windowText(null)).toBe("");
  });
});
