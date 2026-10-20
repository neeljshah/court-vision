import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { ResidualAnatomy } from "./ResidualAnatomy";
import { buildResidualAnatomy, type ResidualAnatomyData } from "@/lib/analytics/residualAnatomy";

const data: ResidualAnatomyData = {
  asOf: null,
  exclusions: [],
  sports: [
    { sport: "mlb", nFiles: 2, nRecords: 12, nSkipped: 3, timeBuckets: ["early", "late"], probBuckets: ["0-.2", ".2-.4"], grid: [], rankings: { byVolume: [], byPerRowError: [] }, segments: [] },
    { sport: "soccer_intl", nFiles: 1, nRecords: 4, nSkipped: 1, timeBuckets: ["0-15"], probBuckets: ["0-.2"], grid: [], rankings: { byVolume: [], byPerRowError: [] }, segments: [] },
  ],
};

function segment(sport: string, timeBucket: string, probBucket: string, n: number, meanAbsResidual: number, totalAbsResidualMass: number) {
  return { sport, timeBucket, probBucket, n, meanAbsResidual, totalAbsResidualMass };
}

for (const sport of data.sports) {
  const rows = sport.sport === "mlb"
    ? [[segment("mlb", "early", "0-.2", 10, 0.2, 2), null], [null, segment("mlb", "late", ".2-.4", 1, 0.8, 0.8)]]
    : [[segment("soccer_intl", "0-15", "0-.2", 4, 0.4, 1.6)]];
  sport.grid = sport.timeBuckets.map((timeBucket, index) => ({ timeBucket, cells: rows[index] }));
  sport.segments = rows.flat().filter((item): item is ReturnType<typeof segment> => item !== null);
  sport.rankings = { byVolume: [...sport.segments].sort((a, b) => b.totalAbsResidualMass - a.totalAbsResidualMass), byPerRowError: [...sport.segments].sort((a, b) => b.meanAbsResidual - a.meanAbsResidual) };
}

describe("ResidualAnatomy", () => {
  beforeEach(() => window.history.replaceState(null, "", "/analytics/residual-anatomy"));
  it("shows the public artifact's source date without inventing an observation window", () => {
    const published = JSON.parse(readFileSync(join(process.cwd(), "public", "data", "showcase", "residual_anatomy.json"), "utf8"));
    render(<ResidualAnatomy data={buildResidualAnatomy(published)} />);
    const receipt = screen.getByRole("button", { name: "descriptive only Source as of 2026-09-16 -- receipt: descriptive_only" });
    expect(receipt).toHaveTextContent("Source as of 2026-09-16");
    fireEvent.click(receipt);
    expect(screen.getByRole("link", { name: "public/data/showcase/residual_anatomy.json" })).toBeInTheDocument();
    expect(screen.queryByText("Date not published.")).not.toBeInTheDocument();
    expect(screen.queryByText(/Observation window/i)).not.toBeInTheDocument();
  });

  it.each([null, "not-a-date"])("keeps missing or invalid source dates unavailable: %s", asOf => {
    render(<ResidualAnatomy data={{ ...data, asOf }} />);
    fireEvent.click(screen.getByRole("button", { name: "descriptive only residual_anatomy.json -- receipt: descriptive_only" }));
    expect(screen.getByText("Date not published.")).toBeInTheDocument();
    expect(screen.queryByText(/Source as of/)).not.toBeInTheDocument();
  });

  it("renders a grid and published counts for each sport", () => {
    render(<ResidualAnatomy data={data} />);
    expect(screen.getByRole("region", { name: "MLB residual grid" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "International soccer residual grid" })).toBeInTheDocument();
    expect(screen.getAllByText(/Sequential scale: 0 to/i)).toHaveLength(data.sports.length);
    expect(screen.getByRole("region", { name: "MLB residual grid" }).querySelector(".ra-cell-missing")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("switches the selected grid measure", () => {
    render(<ResidualAnatomy data={data} />);
    const controls = screen.getByLabelText("Residual metric");
    fireEvent.click(within(controls).getByRole("button", { name: "Rows" }));
    expect(within(controls).getByRole("button", { name: "Rows" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "MLB early, 0-.2 Rows" })).toHaveTextContent("10");
  });

  it("shows all three published values for an inspected cell", () => {
    render(<ResidualAnatomy data={data} />);
    const initial = screen.getByRole("button", { name: "MLB early, 0-.2 Sum of absolute forecast errors" });
    const selected = screen.getByRole("button", { name: "MLB late, .2-.4 Sum of absolute forecast errors" });
    expect(initial).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(selected);
    expect(initial).toHaveAttribute("aria-pressed", "false");
    expect(selected).toHaveAttribute("aria-pressed", "true");
    expect(selected).toHaveAttribute("aria-controls", "ra-selected-segment");
    expect(selected).toHaveClass("ra-cell-selected");
    expect(selected).toHaveTextContent("Selected");
    const inspector = screen.getByLabelText("Selected residual segment");
    expect(within(inspector).getByText("1")).toBeInTheDocument();
    expect(within(inspector).getByText("0.8000")).toBeInTheDocument();
    expect(within(inspector).getByText("0.80")).toBeInTheDocument();
  });

  it("restores a selected cell, marks it, and keeps its explanation in that sport panel", () => {
    window.history.replaceState(null, "", "/analytics/residual-anatomy?sport=soccer_intl&time=0-15&prob=0-.2&metric=n");
    render(<ResidualAnatomy data={data} />);
    const soccerGrid = screen.getByRole("region", { name: "International soccer residual grid" });
    expect(within(soccerGrid).getByRole("button", { name: "International soccer 0-15, 0-.2 Rows" })).toHaveAttribute("aria-pressed", "true");
    const sportPanel = soccerGrid.closest("section");
    expect(sportPanel).not.toBeNull();
    expect(within(sportPanel!).getByLabelText("Selected residual segment")).toHaveTextContent("published segment contains 4 rows");
    expect(new URLSearchParams(window.location.search).get("sport")).toBe("soccer_intl");
  });
  it("inks each grid cell from its own fill and underlines inline prose links", () => {
    render(<ResidualAnatomy data={data} />);
    expect(screen.getByRole("button", { name: "MLB early, 0-.2 Sum of absolute forecast errors" })).toHaveAttribute("data-ink", "light");
    expect(screen.getByRole("button", { name: "MLB late, .2-.4 Sum of absolute forecast errors" })).toHaveAttribute("data-ink", "dark");
    const css = readFileSync(join(process.cwd(), "app", "(analytics)", "analytics", "residual-anatomy", "residual-anatomy.css"), "utf8");
    expect(css).toMatch(/.ra-page p a {[^}]*text-decoration: underline;[^}]*text-underline-offset/);
  });
});
