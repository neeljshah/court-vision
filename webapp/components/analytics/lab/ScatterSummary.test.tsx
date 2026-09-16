import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { summarizeScatter } from "@/lib/analytics/scatterSummary";
import type { LabField, LabRow } from "@/lib/analytics/labTypes";
import { ScatterSummary } from "./ScatterSummary";
import { ScatterPlot } from "./LabPlot";

const x: LabField = { key: "x", label: "Home minus away shooting difference", unit: "pp" };
const y: LabField = { key: "y", label: "Q4 points shift", unit: "number" };
const rows: LabRow[] = [
  { id: "a", label: "Alpha", group: "NBA", values: { x: .01, y: -2 } },
  { id: "b", label: "Beta", group: "NBA", values: { x: .03, y: 4 } },
  { id: "c", label: "Gamma", group: "NBA", values: { x: .08, y: null } },
  { id: "d", label: "Delta", group: "NBA", values: { x: null, y: 10 } },
  { id: "e", label: "Epsilon", group: "NBA", values: { x: null, y: null } },
];

describe("ScatterSummary", () => {
  it("explains the disjoint plotted and omitted counts with paired and available medians", () => {
    render(<ScatterSummary data={summarizeScatter(rows, "x", "y")} x={x} y={y} />);
    const context = screen.getByRole("region", { name: "Paired measurement summary" });
    expect(context).toHaveTextContent("2 / 5 rows plotted");
    for (const [label, count] of [["Both measurements", 2], ["Horizontal only", 1], ["Vertical only", 1], ["Neither measurement", 1]]) {
      expect(within(context).getByText(String(label), { exact: true }).nextElementSibling).toHaveTextContent(String(count));
    }
    fireEvent.click(screen.getByText("Compare medians and calculation"));
    const horizontal = screen.getByRole("region", { name: "Horizontal measurement medians" });
    const vertical = screen.getByRole("region", { name: "Vertical measurement medians" });
    expect(within(horizontal).getByText("Plotted-row median").nextElementSibling).toHaveTextContent("2 pp");
    expect(within(horizontal).getByText("All available-row median").nextElementSibling).toHaveTextContent("3 pp");
    expect(within(vertical).getByText("Plotted-row median").nextElementSibling).toHaveTextContent("1");
    expect(within(vertical).getByText("All available-row median").nextElementSibling).toHaveTextContent("4");
    expect(horizontal).toHaveTextContent("2 rows with both measurements");
    expect(horizontal).toHaveTextContent("3 rows with this measurement");
    expect(context).toHaveTextContent("Counts follow the current search and population");
    expect(context).toHaveTextContent("Source windows can differ");
  });

  it("keeps individual availability when there are no pairs and draws no points", () => {
    render(<ScatterPlot rows={rows.slice(2)} x={x} y={y} onSelect={() => {}} />);
    expect(screen.getByRole("region", { name: "Paired measurement summary" })).toHaveTextContent("0 / 3 rows plotted");
    expect(screen.getByText(/No rows contain both selected measurements/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Inspect/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Compare medians and calculation"));
    const horizontal = screen.getByRole("region", { name: "Horizontal measurement medians" });
    expect(within(horizontal).getByText("Plotted-row median").nextElementSibling).toHaveTextContent("Unavailable");
    expect(within(horizontal).getByText("All available-row median").nextElementSibling).toHaveTextContent("8 pp");
  });

  it("explains identical axes without double-counting rows", () => {
    render(<ScatterPlot rows={rows} x={x} y={x} onSelect={() => {}} />);
    expect(screen.getByRole("region", { name: "Paired measurement summary" })).toHaveTextContent("3 / 5 rows plotted");
    expect(screen.getByText(/Both axes use the same measurement/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Inspect/ })).toHaveLength(3);
  });

  it("recalculates support and medians when the input rows or vertical axis change", () => {
    const { rerender } = render(<ScatterPlot rows={rows} x={x} y={y} onSelect={() => {}} />);
    expect(screen.getAllByRole("button", { name: /^Inspect/ })).toHaveLength(2);
    rerender(<ScatterPlot rows={[rows[2]]} x={x} y={y} onSelect={() => {}} />);
    expect(screen.getByRole("region", { name: "Paired measurement summary" })).toHaveTextContent("0 / 1 rows plotted");
    rerender(<ScatterPlot rows={[rows[2]]} x={x} y={x} onSelect={() => {}} />);
    expect(screen.getByRole("region", { name: "Paired measurement summary" })).toHaveTextContent("1 / 1 rows plotted");
    expect(screen.getByRole("button", { name: /^Inspect Gamma/ })).toBeInTheDocument();
  });
});
