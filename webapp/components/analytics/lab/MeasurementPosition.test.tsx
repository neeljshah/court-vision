import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { MeasurementPosition } from "./MeasurementPosition";
import type { LabField, LabRow } from "@/lib/analytics/labTypes";

const numericField: LabField = { key: "value", label: "Fixture value", unit: "number" };
const percentField: LabField = { key: "rate", label: "Win rate", unit: "percent" };
const numericRows: LabRow[] = [
  { id: "low", label: "Low", group: "Fixture", values: { value: 1 } },
  { id: "selected", label: "Selected", group: "Fixture", values: { value: 2 } },
  { id: "tie", label: "Tie", group: "Fixture", values: { value: 2 } },
  { id: "high", label: "High", group: "Fixture", values: { value: 4 } },
  { id: "missing", label: "Missing", group: "Fixture", values: { value: null } },
];

it("shows strict below, raw ties, and above counts with a text alternative for the position band", () => {
  render(<MeasurementPosition rows={numericRows} field={numericField} selected={numericRows[1]} populationLabel="All published fixture rows" />);
  const context = screen.getByRole("region", { name: "Measurement context" });
  expect(context).toHaveTextContent("5 rows");
  expect(context).toHaveTextContent("4 / 5");
  expect(within(context).getByText("Below selected value").parentElement).toHaveTextContent("1 row");
  expect(within(context).getByText("Equal to selected value").parentElement).toHaveTextContent("2 rows");
  expect(within(context).getByText("Above selected value").parentElement).toHaveTextContent("1 row");
  expect(screen.getByRole("img", { name: /1 row below, 2 rows tied, and 1 row above/i })).toBeInTheDocument();
  expect(context).toHaveTextContent("Each published row has equal weight");
  expect(context).toHaveTextContent("not a quality label");
});

it("keeps missing selected values unavailable without inventing a position", () => {
  render(<MeasurementPosition rows={numericRows} field={numericField} selected={numericRows[4]} populationLabel="All published fixture rows" />);
  const context = screen.getByRole("region", { name: "Measurement context" });
  expect(context).toHaveTextContent("The selected value is unavailable");
  expect(context).toHaveTextContent("4 / 5");
  expect(context.querySelector(".measurement-position-counts")).toBeNull();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

it("expresses percent-field median differences in percentage points", () => {
  const rows: LabRow[] = [
    { id: "lower", label: "Lower", group: "Fixture", values: { rate: .1 } },
    { id: "selected", label: "Selected", group: "Fixture", values: { rate: .3 } },
    { id: "higher", label: "Higher", group: "Fixture", values: { rate: .5 } },
  ];
  render(<MeasurementPosition rows={rows} field={percentField} selected={rows[2]} populationLabel="All published fixture rows" />);
  const difference = screen.getByText("Difference from median").parentElement;
  expect(difference).toHaveTextContent("+20 pp");
  expect(screen.getByText("Median").parentElement).toHaveTextContent("30%");
});

it("uses the supplied reference rows even when the visible search result would be one row", () => {
  render(<MeasurementPosition rows={numericRows} field={numericField} selected={numericRows[1]} populationLabel="All published fixture rows; search ignored" />);
  const context = screen.getByRole("region", { name: "Measurement context" });
  expect(context).toHaveTextContent("All published fixture rows; search ignored");
  expect(context).toHaveTextContent("5 rows");
  expect(context).toHaveTextContent("Text search does not change this reference population");
  fireEvent.click(screen.getByText("Method note"));
  expect(screen.getByText(/Counts use exact raw-value ties/)).toBeInTheDocument();
});
