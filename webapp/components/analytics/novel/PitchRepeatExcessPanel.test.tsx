import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PitchRepeatExcessPanel, loadPitchRepeatExcess } from "./PitchRepeatExcessPanel";

// Renders the committed artifact, not a fixture: if the producer stops publishing a panel
// or renames a field, these assertions fail instead of the page going blank.
const artifact = loadPitchRepeatExcess();
const figure = (caption: RegExp) => screen.getByText(caption).closest("figure") as HTMLElement;
const rowOf = (caption: RegExp, label: string | RegExp) => within(figure(caption)).getByText(label).closest("tr") as HTMLElement;

describe("PitchRepeatExcessPanel", () => {
  it("renders all seven published tables", () => {
    render(<PitchRepeatExcessPanel />);
    for (const caption of [/preregistered claims/, /excess by count class/, /by the raw pre-pitch count/, /by the family of the previous pitch/, /Swings and misses, repeat against switch/, /Called strikes plus swings and misses/, /7. The same swing-and-miss difference/]) {
      expect(screen.getByText(caption)).toBeInTheDocument();
    }
  });

  it("makes every published table focusable and announces the mobile scroll cue", () => {
    render(<PitchRepeatExcessPanel />);
    const regions = screen.getAllByRole("region", { name: /scrollable table/ });
    expect(regions).toHaveLength(7);
    for (const region of regions) expect(region).toHaveAttribute("tabindex", "0");
    expect(new Set(regions.map(region => region.getAttribute("aria-label"))).size).toBe(7);
    expect(screen.getAllByText("Scroll horizontally for all columns")).toHaveLength(7);
  });

  it("states the measured population and the full dropped-pair waterfall", () => {
    render(<PitchRepeatExcessPanel />);
    expect(screen.getByText(/Measured population: 511,807 adjacent pitch pairs over 2,364 games and 864 pitchers/)).toBeInTheDocument();
    expect(screen.getByText(/693,037 pitches in the source table, 514,630 adjacent pairs, 61 dropped for a pitcher change mid plate appearance, 2,384 dropped for a null or non-pitch type code, 378 dropped for having no leave-one-out baseline, 511,807 measured, of which 5,023 carry no per-pitch outcome code/)).toBeInTheDocument();
  });

  it("prints every preregistered claim with the verdict the interval forced", () => {
    render(<PitchRepeatExcessPanel />);
    expect(artifact.preregistered_claims).toHaveLength(3);
    expect(rowOf(/preregistered claims/, /repeat excess is positive overall/)).toHaveTextContent("CONFIRMED");
    expect(rowOf(/preregistered claims/, /larger in pitcher-ahead counts/)).toHaveTextContent("CONTRADICTED");
    expect(rowOf(/preregistered claims/, /lower rate of swings and misses/)).toHaveTextContent("CONTRADICTED");
  });

  it("gives every count class its n, its own-mix baseline and its interval", () => {
    render(<PitchRepeatExcessPanel />);
    const behind = rowOf(/excess by count class/, "pitcher behind");
    expect(behind).toHaveTextContent("180,871");
    expect(behind).toHaveTextContent("+0.0476");
    expect(behind).toHaveTextContent("0.0451 to 0.0502");
    const all = rowOf(/excess by count class/, "all pairs");
    expect(all).toHaveTextContent("511,807");
    expect(all).toHaveTextContent("0.3533");
    expect(all).toHaveTextContent("0.3166");
    expect(all).toHaveTextContent("+0.0367");
  });

  it("carries the ahead-minus-behind contrast that decided the second claim", () => {
    render(<PitchRepeatExcessPanel />);
    expect(within(figure(/excess by count class/)).getByText(/Pitcher-ahead minus pitcher-behind is -0.0081 with interval -0.0113 to -0.0049/)).toBeInTheDocument();
  });

  it("says why the 0-0 count never appears as a destination", () => {
    render(<PitchRepeatExcessPanel />);
    expect(within(figure(/by the raw pre-pitch count/)).getByText(/0-0 count opens a plate appearance/)).toBeInTheDocument();
    expect(rowOf(/by the raw pre-pitch count/, "1-0")).toHaveTextContent("+0.0937");
    expect(rowOf(/by the raw pre-pitch count/, "2-2")).toHaveTextContent("-0.0258");
  });

  it("shows the repeated pitch drawing more swings and misses, not fewer", () => {
    render(<PitchRepeatExcessPanel />);
    const even = rowOf(/Swings and misses, repeat against switch/, "even");
    expect(even).toHaveTextContent("0.1464");
    expect(even).toHaveTextContent("0.1265");
    expect(even).toHaveTextContent("+0.0199");
    expect(even).toHaveTextContent("yes");
    const behind = rowOf(/Swings and misses, repeat against switch/, "pitcher behind");
    expect(behind).toHaveTextContent("-0.0051");
    expect(rowOf(/Swings and misses, repeat against switch/, /standardized over the cells above/)).toHaveTextContent("+0.0098");
  });

  it("publishes the weak-contact comparison as the undecided one", () => {
    render(<PitchRepeatExcessPanel />);
    const row = rowOf(/Called strikes plus swings and misses/, "weak contact -- even");
    expect(row).toHaveTextContent("+0.0053");
    expect(row).toHaveTextContent("no");
    expect(within(figure(/Called strikes plus swings and misses/)).getByText(/\+0.0020 \(-0.0043 to 0.0085\)/)).toBeInTheDocument();
  });

  it("holds the destination family fixed so the comparison is not a type-mix artifact", () => {
    render(<PitchRepeatExcessPanel />);
    expect(rowOf(/7. The same swing-and-miss difference/, "pitcher ahead / breaking")).toHaveTextContent("+0.0372");
    expect(within(figure(/7. The same swing-and-miss difference/)).getByText(/Standardized over these nine cells: \+0.0172/)).toBeInTheDocument();
  });

  it("reports the truncation rebuild and the per-pitcher spread", () => {
    render(<PitchRepeatExcessPanel />);
    expect(screen.getByText(/rebuilt on the 1,191 games through 2025-06-29/)).toBeInTheDocument();
    expect(screen.getByText(/the overall excess is \+0.0360/)).toBeInTheDocument();
    expect(screen.getByText(/389 pitchers at or above 500 pairs/)).toBeInTheDocument();
  });

  it("carries the artifact verdict verbatim", () => {
    render(<PitchRepeatExcessPanel />);
    expect(screen.getByText(artifact.verdict as string)).toBeInTheDocument();
  });
});
