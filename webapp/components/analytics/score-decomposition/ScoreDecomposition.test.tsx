import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScoreDecomposition } from "./ScoreDecomposition";

const sports = [{ sport: "soccer_intl", rows: [{ side: "model" as const, brier: 0.227887, reliability: 0.092837, resolution: 0.038185, uncertainty: 0.238877, reconstructedBrier: 0.293529, remainder: 0.065642 }, { side: "market" as const, brier: 0.142726, reliability: 0.053423, resolution: 0.082761, uncertainty: 0.238877, reconstructedBrier: 0.209538, remainder: 0.066812 }] }];

describe("ScoreDecomposition", () => {
  it("shows the signed six-decimal reconstruction remainder", () => {
    render(<ScoreDecomposition sports={sports} />);
    expect(screen.getByText("0.293529 - 0.227887 =")).toBeInTheDocument();
    expect(screen.getByText("0.065642")).toBeInTheDocument();
  });

  it("keeps the published populations separate", () => {
    render(<ScoreDecomposition sports={sports} />);
    const table = screen.getByRole("table", { name: /brier reconstruction audit/i });
    expect(within(table).getByText("Model")).toBeInTheDocument();
    expect(within(table).getByText("Market")).toBeInTheDocument();
  });

  it("renders a chart and explains the binned reconstruction limit", () => {
    render(<ScoreDecomposition sports={sports} />);
    expect(screen.getByTestId("score-decomposition-chart")).toBeInTheDocument();
    expect(screen.getByText(/can differ from the published Brier/i)).toBeInTheDocument();
  });
});
