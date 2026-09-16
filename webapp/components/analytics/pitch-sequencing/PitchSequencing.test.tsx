import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PitchSequencing } from "./PitchSequencing";

const data = { pitchTypes: ["FF", "SL"], rowMinN: 200, asOf: "2026-07-25", classes: [{ id: "all", definition: "all rows", overlapping: false, coverage: 0.9, rowNFrom: [10, 4], rowBelowFloor: [false, true], countMatrix: [[2, 3], [1, 1]], probabilityMatrix: [[0.2, 0.3], [0.25, 0.25]] }, { id: "two_strike", definition: "overlap", overlapping: true, coverage: 0.8, rowNFrom: [8, 3], rowBelowFloor: [false, false], countMatrix: [[4, 1], [1, 1]], probabilityMatrix: [[0.5, 0.125], [0.2, 0.2]] }] };

describe("PitchSequencing", () => {
  it("maps selected cells to their published row, column, count, and denominator", () => {
    render(<PitchSequencing data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "FF to SL: 30.0%" }));
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
  });

  it("states masked rows and the published floor", () => {
    render(<PitchSequencing data={data} />);
    fireEvent.click(screen.getByRole("button", { name: /SL to FF: masked row/i }));
    expect(screen.getByText(/below the floor of 200 transitions/i)).toBeInTheDocument();
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
    expect(within(tableRegion).getByRole("cell", { name: "SL to FF: masked row" })).toHaveTextContent("Masked");
    fireEvent.click(screen.getByRole("button", { name: "two_strike" }));
    expect(screen.getByRole("region", { name: "two_strike pitch sequencing table" })).toBeInTheDocument();
  });
});
