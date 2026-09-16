import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReliabilityFinding } from "./ReliabilityFinding";

const sports = [{
  sport: "soccer_intl",
  nRows: 9003,
  measurements: [
    { source: "model" as const, n: 9003, brier: 0.227887, reliability: 0.092837, resolution: 0.038185, uncertainty: 0.238877, reconstructedBrier: 0.293529, remainder: -0.065642, reliabilityComparison: "larger" as const },
    { source: "market" as const, n: 9003, brier: 0.142726, reliability: 0.053423, resolution: 0.082761, uncertainty: 0.238877, reconstructedBrier: 0.209538, remainder: -0.066812, reliabilityComparison: "smaller" as const },
  ],
}];

describe("ReliabilityFinding", () => {
  it("renders the soccer derived remainder, component values, and both published denominators", () => {
    render(<ReliabilityFinding sports={sports} />);
    const table = screen.getByRole("table", { name: /international soccer published decomposition audit/i });
    expect(within(table).getByText("-0.065642")).toBeInTheDocument();
    expect(within(table).getAllByText("9,003")[0]).toBeInTheDocument();
    expect(screen.getByText(/Published denominators: 9,003 rows/i)).toBeInTheDocument();
    expect(within(table).getByText(/0\.092837.*0\.038185/)).toBeInTheDocument();
  });

  it("uses a sport-specific larger-than comparison without the former unconditional claim", () => {
    render(<ReliabilityFinding sports={sports} />);
    expect(screen.getByText(/Reliability is larger than resolution/i)).toBeInTheDocument();
    expect(screen.queryByText(/Reliability < resolution here means the miscalibration term is small/i)).not.toBeInTheDocument();
  });
});
