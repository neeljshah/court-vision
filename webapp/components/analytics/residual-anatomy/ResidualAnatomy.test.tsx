import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResidualAnatomy } from "./ResidualAnatomy";
import type { ResidualAnatomyData } from "@/lib/analytics/residualAnatomy";

const data: ResidualAnatomyData = {
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
  it("renders a grid and published counts for each sport", () => {
    render(<ResidualAnatomy data={data} />);
    expect(screen.getByRole("region", { name: "MLB residual grid" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "International soccer residual grid" })).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: "MLB late, .2-.4 Total absolute residual mass" }));
    const inspector = screen.getByLabelText("Selected residual segment");
    expect(within(inspector).getByText("1")).toBeInTheDocument();
    expect(within(inspector).getByText("0.8000")).toBeInTheDocument();
    expect(within(inspector).getByText("0.80")).toBeInTheDocument();
  });
});
