import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RestAsymmetryPanel, loadRestAsymmetry } from "./RestAsymmetryPanel";

// Renders the committed artifact, not a fixture: if the producer stops publishing a
// panel or renames a field, these assertions fail instead of the page going blank.
const artifact = loadRestAsymmetry();
const figure = (caption: RegExp) => screen.getByText(caption).closest("figure") as HTMLElement;
const rowOf = (caption: RegExp, label: string) => within(figure(caption)).getByText(label).closest("tr") as HTMLElement;

describe("RestAsymmetryPanel", () => {
  it("renders all five published panels", () => {
    render(<RestAsymmetryPanel />);
    for (const caption of [/by rest differential/, /against the equal-rest cell/, /Symmetric congestion/, /Season stability/, /minus the recorded reference forecast/]) {
      expect(screen.getByText(caption)).toBeInTheDocument();
    }
  });

  it("keeps the schedule population and the priced subset apart", () => {
    render(<RestAsymmetryPanel />);
    expect(screen.getByText(/Schedule population: 4,793 games/)).toBeInTheDocument();
    expect(screen.getByText(/Priced population: 1,103 games, 2025-26 only/)).toBeInTheDocument();
    expect(screen.getByText(/4,846 games in the source table, 53 dropped for a missing rest day, 0 dropped for a missing outcome, 4,793 measured, 1,103 of those/)).toBeInTheDocument();
  });

  it("gives every rest cell its n, frequency and interval", () => {
    render(<RestAsymmetryPanel />);
    const row = rowOf(/by rest differential/, "home +2 or more");
    expect(row).toHaveTextContent("259");
    expect(row).toHaveTextContent("0.6409");
    expect(row).toHaveTextContent("0.5827 to 0.7016");
    expect(artifact.panels.rest_differential.cells).toHaveLength(within(figure(/by rest differential/)).getAllByRole("row").length - 1);
  });

  it("shows the one contrast whose interval excludes zero", () => {
    render(<RestAsymmetryPanel />);
    const row = rowOf(/against the equal-rest cell/, "home +2 or more");
    expect(row).toHaveTextContent("0.0892");
    expect(row).toHaveTextContent("0.0257 to 0.1502");
    expect(row).toHaveTextContent("yes");
    expect(rowOf(/against the equal-rest cell/, "away +1")).toHaveTextContent("no");
  });

  it("keeps a masked cell's count and prints its reason", () => {
    render(<RestAsymmetryPanel />);
    const row = rowOf(/Symmetric congestion/, "mixed");
    expect(row).toHaveTextContent("no games in this cell");
    expect(row.className).toContain("ra-masked");
    expect(rowOf(/Symmetric congestion/, "both on a back-to-back")).toHaveTextContent("245");
  });

  it("does not read the congestion similarity as absence of fatigue", () => {
    render(<RestAsymmetryPanel />);
    expect(within(figure(/Symmetric congestion/)).getByText(/do not establish absence of fatigue/)).toBeInTheDocument();
  });

  it("publishes the season rows the pooled gradient averages over", () => {
    render(<RestAsymmetryPanel />);
    expect(rowOf(/Season stability/, "2025-26")).toHaveTextContent("0.0114");
    expect(rowOf(/Season stability/, "2024-25")).toHaveTextContent("0.1162");
  });

  it("prints the reference-forecast gap with the width that makes the extreme cells undecidable", () => {
    render(<RestAsymmetryPanel />);
    const thin = rowOf(/minus the recorded reference forecast/, "away +2 or more");
    expect(thin).toHaveTextContent("-0.1942 to 0.1186");
    expect(thin).toHaveTextContent("0.3128");
    expect(rowOf(/minus the recorded reference forecast/, "home +2 or more")).toHaveTextContent("0.2310");
    expect(within(figure(/minus the recorded reference forecast/)).getByText(/no quote timestamp/)).toBeInTheDocument();
  });

  it("carries the artifact verdict verbatim", () => {
    render(<RestAsymmetryPanel />);
    expect(screen.getByText(artifact.verdict as string)).toBeInTheDocument();
  });
});
