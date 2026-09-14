import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ComparisonEntity } from "@/lib/analytics/comparisonData";
import { TennisSurfaceComparison } from "./TennisSurfaceComparison";

const a: ComparisonEntity = {
  slug: "alpha", name: "Alpha (ATP)", asOf: "2026-07-19", status: "partial", floors: "hard_n>=30 | clay_n>=30",
  values: { hard_wr_career: .69, hard_wr_recent: .66, clay_wr_career: .74, clay_minus_hard_career: .05, clay_wr_recent: .72, clay_minus_hard_recent: .06 },
  percentiles: { hard_wr_career: 80, clay_wr_career: 90, clay_minus_hard_career: 70 },
};
const b: ComparisonEntity = {
  slug: "beta", name: "Beta (ATP)", asOf: "2026-07-19", status: "partial", floors: "hard_n>=30 | clay_n>=30 | grass_n>=30",
  values: { hard_wr_career: .5, clay_wr_career: .4 }, percentiles: { hard_wr_career: 20, clay_wr_career: 10 },
};

describe("TennisSurfaceComparison", () => {
  it("shows paired raw surface records, preserves asymmetric unavailable values, and changes surfaces", () => {
    const onSurfaceChange = vi.fn();
    render(<TennisSurfaceComparison a={a} b={b} surface="hard" onSurfaceChange={onSurfaceChange} sourceHref="/data/showcase/atlas_tennis_manifest.json" nRankedByMetric={{ hard_wr_career: 2, hard_wr_recent: 0 }} />);
    expect(screen.getByRole("heading", { name: "Recorded surface history" })).toBeInTheDocument();
    expect(screen.getByText("69.0%")).toBeInTheDocument();
    expect(screen.getByText("50.0%")).toBeInTheDocument();
    expect(screen.getByText("Not reported")).toBeInTheDocument();
    expect(screen.getByText("Not ranked")).toBeInTheDocument();
    expect(screen.getByText("80th percentile")).toBeInTheDocument();
    expect(screen.getAllByText("Ranked among 2 profiles")).toHaveLength(2);
    expect(screen.getByText(/not head-to-head results or forecasts/i)).toBeInTheDocument();
    expect(screen.getByText(/Career: 2015-2025 pooled/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clay" }));
    expect(onSurfaceChange).toHaveBeenCalledWith("clay");
  });

  it("renders the explicit empty state when neither profile has a published surface measurement", () => {
    render(<TennisSurfaceComparison a={{ ...a, values: {}, percentiles: {} }} b={{ ...b, values: {}, percentiles: {} }} surface="grass" onSurfaceChange={vi.fn()} sourceHref="/data/showcase/atlas_tennis_manifest.json" />);
    expect(screen.getByText(/No published grass measurements/)).toBeInTheDocument();
    expect(screen.getByText(/Source date:/)).toBeInTheDocument();
    expect(screen.getByTitle("2026-07-19")).toBeInTheDocument();
  });

  it("keeps a zero record ranked while suppressing malformed surface ranks", () => {
    render(<TennisSurfaceComparison a={{ ...a, values: { hard_wr_career: 0, hard_wr_recent: NaN }, percentiles: { hard_wr_career: 0, hard_wr_recent: 50 } }} b={{ ...b, values: { hard_wr_career: .5, hard_wr_recent: .5 }, percentiles: { hard_wr_career: Infinity, hard_wr_recent: 101 } }} surface="hard" onSurfaceChange={vi.fn()} sourceHref="/data/showcase/atlas_tennis_manifest.json" nRankedByMetric={{ hard_wr_career: 2, hard_wr_recent: 2 }} />);
    expect(screen.getByText("0.0%")).toBeInTheDocument();
    expect(screen.getByText("0th percentile")).toBeInTheDocument();
    expect(screen.getAllByText("Ranked among 2 profiles")).toHaveLength(1);
    expect(screen.getAllByText("Not ranked")).toHaveLength(2);
    expect(screen.queryByText("101st percentile")).not.toBeInTheDocument();
  });
});
