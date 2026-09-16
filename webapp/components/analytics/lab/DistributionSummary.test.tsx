import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { DistributionPlot, DistributionSummary } from "./DistributionSummary";
import type { LabField, LabRow } from "@/lib/analytics/labTypes";
const field: LabField = { key: "rate", label: "Win-rate difference", unit: "pp" };
const rows: LabRow[] = [0, .1, .2, null].map((rate, i) => ({ id: String(i), label: String(i), group: "Fixture", values: { rate } }));

it("reports measured coverage and percentage-point summaries without hiding missing rows", () => {
  render(<DistributionSummary rows={rows} field={field} />);
  const summary = screen.getByRole("region", { name: "Measurement summary" });
  expect(summary).toHaveTextContent("3 / 4");
  expect(summary).toHaveTextContent("1 unavailable");
  expect(summary).toHaveTextContent("5 pp to 15 pp");
  expect(summary).toHaveTextContent("0 pp to 20 pp");
  expect(summary).toHaveTextContent("Row counts are not independent game or event counts");
  expect(summary.querySelectorAll("dl > div")).toHaveLength(4);
  expect(summary.querySelectorAll("dl > div > span")).toHaveLength(0);
});

it("provides an accessible bin table and calculation alongside the histogram", () => {
  render(<DistributionPlot rows={rows} field={field} />);
  expect(screen.getByRole("img", { name: /Win-rate difference histogram, 2 bins/ })).toBeInTheDocument();
  fireEvent.click(screen.getByText("Bin counts and calculation"));
  const table = screen.getByRole("table", { name: "Win-rate difference: histogram counts" });
  expect(within(table).getAllByRole("row")).toHaveLength(3);
  expect(table).toHaveTextContent("0 pp to below 10 pp");
  expect(table).toHaveTextContent("10 pp to and including 20 pp");
  expect(table).toHaveTextContent("66.7%");
  expect(screen.getByText(/Quartiles use linear interpolation/)).toHaveTextContent("R7 method");
});

it("states constant and unavailable populations directly", () => {
  const { rerender } = render(<DistributionPlot rows={[rows[0]]} field={field} />);
  expect(screen.getByText("Every measured row has the same value: 0 pp.")).toBeInTheDocument();
  rerender(<DistributionPlot rows={[rows[3]]} field={field} />);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.getByText(/No numeric measurements are available/)).toBeInTheDocument();
});

it("labels a percentage distribution's spread in percentage points", () => {
  render(<DistributionPlot rows={rows} field={{ ...field, label: "Win rate", unit: "percent" }} />);
  expect(screen.getByText("Interquartile range")).toHaveTextContent("10 pp");
  expect(screen.getByText("Mean")).toHaveTextContent("10%");
});
