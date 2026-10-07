import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { StateReliabilityRows } from "./StateReliabilityRows";
import type { StateReliabilityRow, StateReliabilitySport } from "@/lib/analytics/stateReliability";
import { exportStateReliabilityCSV } from "@/lib/analytics/stateReliabilityCsv";

vi.mock("@/lib/analytics/stateReliabilityCsv", () => ({ exportStateReliabilityCSV: vi.fn() }));

function row(source: "model" | "market", timeBucket: string, n: number, error: number): StateReliabilityRow {
  return { sport: "mlb", source, timeBucket, probabilityBucket: ".4-.6", n, meanP: .5, meanY: .5 - error, calibrationError: error };
}
const sport: StateReliabilitySport = {
  sport: "mlb", artifactDate: "2026-07-25", nForecastObservations: 660, nSkippedNoStateField: 0,
  nCells: 2, timeBuckets: ["early", "late"], probabilityBuckets: [".4-.6"],
  rows: [row("model", "early", 10, 0), row("model", "late", 100, .2), row("market", "late", 500, .03), row("market", "early", 50, .03)],
};
const choose = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const tableRows = () => within(screen.getByRole("table")).getAllByRole("row").slice(1);
const supports = () => tableRows().map(item => within(item).getAllByRole("cell")[3].textContent);

it("combines source, phase and inclusive support filters without altering measurements", () => {
  render(<StateReliabilityRows sport={sport} label="MLB" />);
  choose("Row source", "model"); choose("Row time bucket", "late"); choose("Minimum row support", "100");
  expect(screen.getByRole("status")).toHaveTextContent("Showing 1 of 4 published rows for MLB.");
  expect(tableRows()).toHaveLength(1);
  expect(within(tableRows()[0]).getAllByRole("cell").map(cell => cell.textContent)).toEqual([
    "Model", "late", ".4-.6", "100", "50.00%", "30.00%", "-20.00 pp", "20.00 pp",
  ]);
});

it("sorts gaps and support numerically, marks the sorted column, and retains zero", () => {
  const original = JSON.stringify(sport.rows);
  render(<StateReliabilityRows sport={sport} label="MLB" />);
  choose("Row order", "gap-desc");
  expect(supports()).toEqual(["100", "500", "50", "10"]);
  expect(screen.getByRole("columnheader", { name: "Absolute gap (pp)" })).toHaveAttribute("aria-sort", "descending");
  choose("Row order", "support-asc");
  expect(supports()).toEqual(["10", "50", "100", "500"]);
  expect(screen.getByRole("columnheader", { name: /^n$/ })).toHaveAttribute("aria-sort", "ascending");
  expect(screen.getByRole("columnheader", { name: "Absolute gap (pp)" })).not.toHaveAttribute("aria-sort");
  expect(within(tableRows()[0]).getAllByText("0.00 pp")).toHaveLength(2);
  expect(JSON.stringify(sport.rows)).toBe(original);
});

it("explains an empty filtered cohort and restores original order and all rows", () => {
  render(<StateReliabilityRows sport={sport} label="MLB" />);
  choose("Row source", "market"); choose("Row order", "gap-asc"); choose("Minimum row support", "1000");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Showing 0 of 4");
  expect(screen.getByText(/No published rows match these filters/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Download visible rows (CSV)" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Reset table" }));
  expect(supports()).toEqual(["10", "100", "500", "50"]);
  expect(screen.getByRole("table", { name: "All published state-conditioned rows for MLB" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reset table" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Download visible rows (CSV)" })).toBeEnabled();
});

it("downloads the visible filtered rows in the selected order with their source context", () => {
  render(<StateReliabilityRows sport={sport} label="MLB" />);
  choose("Row source", "market"); choose("Minimum row support", "50"); choose("Row order", "support-asc");
  fireEvent.click(screen.getByRole("button", { name: "Download visible rows (CSV)" }));
  expect(exportStateReliabilityCSV).toHaveBeenLastCalledWith(sport, [sport.rows[3], sport.rows[2]]);
  expect(screen.getByText(/observation dates are not published/)).toBeInTheDocument();
});
