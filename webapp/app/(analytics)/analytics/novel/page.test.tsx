import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NovelStatsPage from "./page";

describe("NovelStatsPage", () => {
  it("keeps the Load-Bearing Index estimator observation windows separate", () => {
    render(<NovelStatsPage />);
    expect(screen.getByText(/Estimator A: observation window: 2024-25/)).toBeInTheDocument();
    expect(screen.getByText(/Estimator B: observation window: 2025-26 regular season/)).toBeInTheDocument();
  });
});
