import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NovelStatsPage from "./page";

describe("NovelStatsPage", () => {
  it("keeps the Load-Bearing Index estimator observation windows separate", () => {
    render(<NovelStatsPage />);
    expect(screen.getByText(/Estimator A: Observation window 2024-25/)).toBeInTheDocument();
    expect(screen.getByText(/Estimator B: Observation window 2025-26 regular season/)).toBeInTheDocument();
  });

  it("states the honest null as retained evidence instead of a trust argument", () => {
    render(<NovelStatsPage />);
    expect(screen.queryByText(/reason to trust/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/This measurement records a market overshoot/).length).toBeGreaterThan(0);
  });
});
