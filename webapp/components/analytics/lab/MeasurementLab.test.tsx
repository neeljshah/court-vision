import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MeasurementLab from "./MeasurementLab";
import { ScatterPlot } from "./LabPlot";
import type { LabData, LabField, LabRow } from "@/lib/analytics/labTypes";

const fixture: LabData = {
  datasets: [
    {
      id: "cross-sport", title: "Cross-sport metric", sport: "all", category: "Experimental metrics",
      source: "novel_line_half_life", description: "A cross-sport fixture.", scope: "Fixture scope.", caveat: "Fixture caveat.", status: "Descriptive",
      fields: [{ key: "value", label: "Value", unit: "number" }],
      rows: [
        { id: "mlb", label: "MLB", group: "MLB", values: { value: 2 } },
        { id: "tennis", label: "TENNIS", group: "TENNIS", values: { value: 1 } },
        { id: "missing", label: "Missing value", group: "MLB", values: { value: null } },
      ],
    },
    {
      id: "nba-profile", title: "NBA profile", sport: "nba", category: "Player & team",
      source: "nba_consistency_profiles", description: "An NBA fixture.", scope: "Fixture scope.", caveat: "Fixture caveat.", status: "Descriptive",
      fields: [{ key: "value", label: "Value", unit: "number" }],
      rows: [{ id: "jokic", label: "Nikola Jokic", group: "Published rows", values: { value: 7 }, note: "Fixture detail." }],
    },
  ],
  novel: [],
};

beforeEach(() => window.history.replaceState(null, "", "/analytics/lab"));
afterEach(() => vi.unstubAllGlobals());

describe("MeasurementLab sport filtering and inspection", () => {
  it("filters cross-sport rows and preserves an honest empty state", () => {
    render(<MeasurementLab data={fixture} />);
    fireEvent.change(screen.getByLabelText("Filter lab by sport"), { target: { value: "tennis" } });

    expect(screen.getByRole("status")).toHaveTextContent("1 published row matches");
    expect(screen.getByRole("button", { name: /Inspect TENNIS/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Inspect MLB/ })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filter lab by sport"), { target: { value: "nba" } });
    expect(screen.getByText(/No published measurements for Basketball in this metric/)).toBeInTheDocument();
  });

  it("selects a metric category dataset and opens row details", () => {
    render(<MeasurementLab data={fixture} />);
    fireEvent.click(screen.getByRole("button", { name: /NBA profile/ }));
    fireEvent.click(screen.getByRole("button", { name: /Inspect Nikola Jokic/ }));

    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("Nikola Jokic");
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("Fixture detail.");
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("7");
  });

  it("keeps scatter labels readable in a narrow container and selects a point by keyboard", () => {
    let resize: ((entries: Array<{ contentRect: { width: number } }>) => void) | undefined;
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: (entries: Array<{ contentRect: { width: number } }>) => void) { resize = callback; }
      observe() {} disconnect() {}
    });
    render(<MeasurementLab data={fixture} />);
    fireEvent.click(screen.getByRole("button", { name: "Scatter plot" }));
    act(() => resize?.([{ contentRect: { width: 300 } }]));

    expect(screen.getByRole("group", { name: /Value against Value/ })).toHaveAttribute("viewBox", "0 0 300 280");
    expect(screen.queryByRole("button", { name: /Inspect Missing value/ })).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("button", { name: /Inspect MLB/ }), { key: "Enter" });
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("MLB");
  });

  it("measures an initially empty scatter before constant values arrive", () => {
    let resize: ((entries: Array<{ contentRect: { width: number } }>) => void) | undefined;
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: (entries: Array<{ contentRect: { width: number } }>) => void) { resize = callback; }
      observe() {} disconnect() {}
    });
    const field: LabField = { key: "value", label: "Speed", unit: "mph" };
    const constant: LabRow[] = [{ id: "constant", label: "Constant value", group: "Fixture", values: { value: 0 } }];
    function DeferredScatter() { const [rows, setRows] = useState<LabRow[]>([{ id: "missing", label: "Missing", group: "Fixture", values: { value: null } }]); return <><button onClick={() => setRows(constant)}>Load measurements</button><ScatterPlot rows={rows} x={field} y={field} onSelect={() => undefined} /></>; }
    render(<DeferredScatter />);
    act(() => resize?.([{ contentRect: { width: 300 } }]));
    fireEvent.click(screen.getByRole("button", { name: "Load measurements" }));

    expect(screen.getByRole("group", { name: /Speed against Speed/ })).toHaveAttribute("viewBox", "0 0 300 280");
    const point = screen.getByRole("button", { name: /Inspect Constant value/ });
    expect(point.getAttribute("cx")).not.toMatch(/NaN|Infinity/);
    expect(point.getAttribute("cy")).not.toMatch(/NaN|Infinity/);
  });
});
