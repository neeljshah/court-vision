import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScoreDecomposition } from "./ScoreDecomposition";
import ScoreDecompositionPage from "@/app/(analytics)/analytics/score-decomposition/page";
import publishedDecomposition from "@/public/data/showcase/murphy_decomposition.json";

const sports = [
  { sport: "mlb", nRows: 78986, rows: [{ side: "model" as const, n: 78986, brier: 0.237684, reliability: 0.012701, resolution: 0.023628, uncertainty: 0.248092, reconstructedBrier: 0.237166, remainder: -0.000518 }, { side: "market" as const, n: 78986, brier: 0.206653, reliability: 0.006061, resolution: 0.047124, uncertainty: 0.248092, reconstructedBrier: 0.20703, remainder: 0.000377 }] },
  { sport: "soccer_intl", nRows: 9003, rows: [{ side: "model" as const, n: 9003, brier: 0.227887, reliability: 0.092837, resolution: 0.038185, uncertainty: 0.238877, reconstructedBrier: 0.293529, remainder: 0.065642 }, { side: "market" as const, n: 9003, brier: 0.142726, reliability: 0.053423, resolution: 0.082761, uncertainty: 0.238877, reconstructedBrier: 0.209538, remainder: 0.066812 }] },
];

describe("ScoreDecomposition", () => {
  it("carries the actual snapshot source date through the page to its chart receipt", () => {
    render(<ScoreDecompositionPage />);
    const figure = screen.getByTestId("score-decomposition-chart").closest("figure")!;
    expect(within(figure).getByText(`Source as of ${publishedDecomposition.as_of}`)).toBeInTheDocument();
    expect(within(figure).queryByText("Date not published.")).not.toBeInTheDocument();
    expect(within(figure).queryByText(/Observation window|Snapshot generated/)).not.toBeInTheDocument();
  });

  it("retains the explicit missing-date state when no source date is supplied", () => {
    render(<ScoreDecomposition sports={sports} />);
    expect(screen.getByText("Date not published.")).toBeInTheDocument();
  });

  it("shows the signed six-decimal reconstruction remainder", () => {
    render(<ScoreDecomposition sports={sports} />);
    expect(screen.getByText((_, element) => element?.textContent === "0.293529 - 0.227887 = 0.065642")).toBeInTheDocument();
    expect(screen.getByText("0.065642")).toBeInTheDocument();
  });

  it("keeps the published populations separate", () => {
    render(<ScoreDecomposition sports={sports} />);
    const table = screen.getByRole("table", { name: /brier reconstruction audit/i });
    expect(within(table).getAllByText("Model")[0]).toBeInTheDocument();
    expect(within(table).getAllByText("Market").length).toBeGreaterThan(0);
  });

  it("shows real published sport and source denominators for both sports", () => {
    render(<ScoreDecomposition sports={sports} />);
    const table = screen.getByRole("table", { name: /brier reconstruction audit/i });
    expect(within(table).getAllByText("n rows=78,986")).toHaveLength(2);
    expect(within(table).getAllByText("n=78,986")).toHaveLength(2);
    expect(within(table).getAllByText("n rows=9,003")).toHaveLength(2);
    expect(within(table).getAllByText("n=9,003")).toHaveLength(2);
  });

  it("renders a chart and explains the binned reconstruction limit", () => {
    render(<ScoreDecomposition sports={sports} />);
    expect(screen.getByTestId("score-decomposition-chart")).toBeInTheDocument();
    expect(screen.getByText(/can differ from the published Brier/i)).toBeInTheDocument();
  });
});
