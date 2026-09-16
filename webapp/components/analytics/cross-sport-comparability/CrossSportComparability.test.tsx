import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CrossSportComparability } from "./CrossSportComparability";
import type { CrossSportComparability as ComparabilityData } from "@/lib/analytics/crossSportComparability";

const data: ComparabilityData = {
  generatedAt: "2026-07-22T22:55:23.467132+00:00",
  capabilities: [],
  rows: [],
  comparableRows: [
    { id: "mlb-0", sport: "mlb", market: "moneyline_ingame", reliability_model: 0.012701, reliability_market: 0.006061, reliability_gap: 0.00664, reliability_unit: "brier", reliability_comparable: true, comparability_reason: "same scale", n: 78986, sources: [], evidence: { href: "/analytics/score-decomposition", title: "Score decomposition" }, unavailableMeasurement: null },
    { id: "soccer-0", sport: "soccer_intl", market: "moneyline_ingame", reliability_model: 0.092837, reliability_market: 0.053423, reliability_gap: 0.039414, reliability_unit: "brier", reliability_comparable: true, comparability_reason: "same scale", n: 9003, sources: [], evidence: { href: "/analytics/score-decomposition", title: "Score decomposition" }, unavailableMeasurement: null },
  ],
  unsupportedRows: [
    { id: "mlb-1", sport: "mlb", market: "totals", reliability_model: null, reliability_market: null, reliability_gap: null, reliability_unit: null, reliability_comparable: false, comparability_reason: "CRPS reason verbatim", n: 671, sources: [], evidence: { href: "/analytics/m/kernel_transfer", title: "Kernel Transfer evidence" }, unavailableMeasurement: "Murphy reliability/resolution" },
    { id: "nba-0", sport: "nba", market: "winprob", reliability_model: null, reliability_market: null, reliability_gap: null, reliability_unit: null, reliability_comparable: false, comparability_reason: "NBA reason verbatim", n: 6371, sources: [], evidence: { href: "/analytics/m/kernel_transfer", title: "Kernel Transfer evidence" }, unavailableMeasurement: "10-bin Murphy split" },
    { id: "tennis-0", sport: "tennis", market: "prior", reliability_model: null, reliability_market: null, reliability_gap: null, reliability_unit: null, reliability_comparable: false, comparability_reason: "Tennis reason verbatim", n: 55075, sources: [], evidence: { href: "/analytics/m/kernel_transfer", title: "Kernel Transfer evidence" }, unavailableMeasurement: "market probability" },
  ],
};

describe("CrossSportComparability", () => {
  it("lists exactly the two comparable rows in the chart and supported list", () => {
    render(<CrossSportComparability data={data} />);
    const chart = screen.getByTestId("comparability-chart");
    expect(within(chart).getAllByTestId("comparable-chart-row")).toHaveLength(2);
    expect(within(screen.getByLabelText("Comparable reliability rows")).getAllByRole("link")).toHaveLength(2);
  });

  it("lists all three unsupported reasons verbatim", () => {
    render(<CrossSportComparability data={data} />);
    const rows = screen.getAllByTestId("unsupported-row");
    expect(rows).toHaveLength(3);
    expect(rows.map(row => row.textContent)).toEqual(expect.arrayContaining([expect.stringContaining("CRPS reason verbatim"), expect.stringContaining("NBA reason verbatim"), expect.stringContaining("Tennis reason verbatim")]));
  });

  it("renders every evidence destination as a route link", () => {
    render(<CrossSportComparability data={data} />);
    const links = screen.getAllByRole("link", { name: /view/i });
    expect(links).toHaveLength(5);
    expect(links.map(link => link.getAttribute("href"))).toEqual(["/analytics/score-decomposition", "/analytics/score-decomposition", "/analytics/m/kernel_transfer", "/analytics/m/kernel_transfer", "/analytics/m/kernel_transfer"]);
  });
});
