import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { PitchSequencing } from "./PitchSequencing";

const data = { pitchTypes: ["FF", "SL"], rowMinN: 200, asOf: "2026-07-25", classes: [{ id: "all", definition: "all rows", overlapping: false, coverage: 0.9, rowNFrom: [10, 4], rowBelowFloor: [false, true], countMatrix: [[2, 3], [1, 1]], probabilityMatrix: [[0.2, 0.3], [0.25, 0.25]] }, { id: "two_strike", definition: "overlap", overlapping: true, coverage: 0.8, rowNFrom: [8, 3], rowBelowFloor: [false, false], countMatrix: [[4, 1], [1, 1]], probabilityMatrix: [[0.5, 0.125], [0.2, 0.2]] }] };

describe("PitchSequencing", () => {
  beforeEach(() => window.history.replaceState(null, "", "/analytics/pitch-sequencing"));
  it("maps selected cells to their published row, column, count, and denominator", () => {
    render(<PitchSequencing data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "FF to SL: 30.0%" }));
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
    expect(screen.getAllByText("10").length).toBeGreaterThan(0);
  });

  it("states masked rows and the published floor", () => {
    render(<PitchSequencing data={data} />);
    expect(screen.getByTestId("pitch-sequencing-heatmap").querySelector(".ps-cell-missing")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /SL to FF: masked row/i }));
    expect(screen.getByText(/below the floor of 200 transitions/i)).toBeInTheDocument();
  });

  it("labels the shared probability scale and retains selected cells", () => {
    render(<PitchSequencing data={data} />);
    expect(screen.getByText(/Sequential scale: 0.0% to 30.0%/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "FF to SL: 30.0%" }));
    expect(screen.getByTestId("pitch-sequencing-heatmap").querySelector(".ps-selected")).toBeInTheDocument();
  });

  it("retains the overlap explanation and unnormalized row note", () => {
    render(<PitchSequencing data={data} />);
    expect(screen.getByText(/overlapping views, not additive/i)).toBeInTheDocument();
    expect(screen.getByText(/Rows can total below 100%/i)).toBeInTheDocument();
  });

  it("publishes an accessible companion table for the selected class", () => {
    render(<PitchSequencing data={data} />);
    const tableRegion = screen.getByRole("region", { name: "all pitch sequencing table" });
    expect(within(tableRegion).getByRole("table", { name: "all conditional pitch sequencing probabilities" })).toBeInTheDocument();
    expect(within(tableRegion).getByRole("cell", { name: "FF to SL: 30.0%; count 3" })).toHaveTextContent("30.0%");
    expect(within(tableRegion).getByRole("cell", { name: /^SL to FF: masked row/ })).toHaveTextContent("Masked");
    fireEvent.click(screen.getByRole("button", { name: "two_strike" }));
    expect(screen.getByRole("region", { name: "two_strike pitch sequencing table" })).toBeInTheDocument();
  });

  it("renders every class with complete rows, columns, and published denominators", () => {
    render(<PitchSequencing data={data} />);
    for (const item of data.classes) {
      fireEvent.click(screen.getByRole("button", { name: item.id }));
      const table = within(screen.getByRole("region", { name: `${item.id} pitch sequencing table` })).getByRole("table");
      expect(within(table).getAllByRole("row")).toHaveLength(data.pitchTypes.length + 1);
      expect(within(table).getAllByRole("columnheader")).toHaveLength(data.pitchTypes.length + 2);
      expect(within(table).getAllByRole("button", { name: /Select/ })).toHaveLength(data.pitchTypes.length ** 2);
      expect(within(table).getByRole("row", { name: new RegExp(`FF ${item.rowNFrom[0]}`) })).toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole("button", { name: "all" }));
    const table = within(screen.getByRole("region", { name: "all pitch sequencing table" })).getByRole("table");
    expect(within(table).getByRole("row", { name: /SL 4/i })).toHaveTextContent("Masked below floor");
  });

  it("restores a shared class and cell selection from the permalink", () => {
    window.history.replaceState(null, "", "/analytics/pitch-sequencing?class=two_strike&from=SL&to=FF");
    render(<PitchSequencing data={data} />);
    expect(screen.getByRole("button", { name: "two_strike" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Select SL to FF" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("1")).toBeInTheDocument();
  });
  it("inks each cell from its own fill and keeps the heatmap out of the img role", () => {
    render(<PitchSequencing data={data} />);
    const heatmap = screen.getByTestId("pitch-sequencing-heatmap");
    expect(heatmap).not.toHaveAttribute("role", "img");
    expect(heatmap.querySelectorAll("[role='button']")).toHaveLength(data.pitchTypes.length ** 2);
    fireEvent.click(screen.getByRole("button", { name: "two_strike" }));
    expect(screen.getByRole("button", { name: "FF to FF: 50.0%" }).querySelector("text")).toHaveAttribute("data-ink", "light");
    expect(screen.getByRole("button", { name: "FF to SL: 12.5%" }).querySelector("text")).toHaveAttribute("data-ink", "dark");
    expect(screen.getByRole("button", { name: "Select FF to FF" })).toHaveAttribute("data-ink", "light");
    expect(screen.getByRole("button", { name: "Select FF to SL" })).toHaveAttribute("data-ink", "dark");
  });
});
