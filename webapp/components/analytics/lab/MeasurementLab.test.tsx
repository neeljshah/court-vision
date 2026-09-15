import { act, fireEvent, render, screen } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
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
      fields: [{ key: "value", label: "Value", unit: "number" }, { key: "alt", label: "Alternate", unit: "number" }],
      rows: [
        { id: "mlb", label: "MLB", group: "MLB", values: { value: 2, alt: 1 } },
        { id: "tennis", label: "TENNIS", group: "TENNIS", values: { value: 1, alt: 2 } },
        { id: "missing", label: "Missing value", group: "MLB", values: { value: null, alt: null } },
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
  it("restores a distribution URL and preserves unavailable coverage", () => {
    window.history.replaceState(null, "", "?sport=mlb&dataset=cross-sport&view=distribution");
    render(<MeasurementLab data={fixture} />);
    expect(screen.getByRole("button", { name: "Distribution", exact: true })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", { name: "Measurement summary" })).toHaveTextContent("1 / 2");
    expect(screen.getByRole("region", { name: "Measurement summary" })).toHaveTextContent("1 unavailable");
    expect(screen.getByRole("region", { name: "Measurement distribution" })).toHaveTextContent("Every measured row has the same value: 2");
  });

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

  it("focuses selected details and restores its row after Escape", () => {
    render(<MeasurementLab data={fixture} />);
    fireEvent.click(screen.getByRole("button", { name: /NBA profile/ }));
    const row = screen.getByRole("button", { name: /Inspect Nikola Jokic/ });
    row.focus();
    fireEvent.click(row);
    const details = screen.getByRole("region", { name: "Selected measurement" });
    expect(details).toHaveFocus();
    const close = screen.getByRole("button", { name: "Close measurement details" });
    close.focus();
    fireEvent.keyDown(close, { key: "Escape" });

    expect(screen.queryByRole("region", { name: "Selected measurement" })).not.toBeInTheDocument();
    expect(window.location.search).not.toContain("row=jokic");
    expect(row).toHaveFocus();
  });

  it("restores a shareable filtered table view and selected row on reload", () => {
    window.history.replaceState(null, "", "/analytics/lab?sport=all&dataset=cross-sport&field=alt&other=value&group=MLB&order=asc&view=scatter&q=MLB&row=mlb");
    render(<MeasurementLab data={fixture} />);

    expect(screen.getByLabelText("Choose dataset")).toHaveValue("cross-sport");
    expect(screen.getByLabelText("Primary measurement")).toHaveValue("alt");
    expect(screen.getByLabelText("Vertical measurement")).toHaveValue("value");
    expect(screen.getByLabelText("Published group")).toHaveValue("MLB");
    expect(screen.getByRole("button", { name: "Scatter plot" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("MLB");
    expect(window.location.search).toContain("row=mlb");
  });

  it("falls back safely from malformed lab view parameters", () => {
    window.history.replaceState(null, "", "/analytics/lab?sport=cricket&dataset=missing&field=wrong&other=bad&group=unknown&order=sideways&view=map&row=nope");
    render(<MeasurementLab data={fixture} />);

    expect(screen.getByLabelText("Filter lab by sport")).toHaveValue("all");
    expect(screen.getByLabelText("Choose dataset")).toHaveValue("cross-sport");
    expect(screen.getByLabelText("Primary measurement")).toHaveValue("value");
    expect(screen.getByRole("button", { name: "Ranked bars" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("region", { name: "Selected measurement" })).not.toBeInTheDocument();
  });

  it("restores browser navigation and clears stale selected rows after filtering", () => {
    render(<MeasurementLab data={fixture} />);
    window.history.replaceState(null, "", "/analytics/lab?sport=all&dataset=cross-sport&field=value&other=value&group=all&order=desc&view=rank&q=&row=mlb");
    act(() => window.dispatchEvent(new PopStateEvent("popstate")));
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("MLB");

    fireEvent.change(screen.getByLabelText("Search measurement rows"), { target: { value: "TENNIS" } });
    expect(screen.queryByRole("region", { name: "Selected measurement" })).not.toBeInTheDocument();
    expect(window.location.search).not.toContain("row=mlb");
  });

  it("hydrates a deep URL without a recoverable mismatch", async () => {
    const markup = renderToString(<MeasurementLab data={fixture} />);
    const container = document.createElement("div");
    container.innerHTML = markup;
    document.body.append(container);
    window.history.replaceState({ next: "metadata" }, "", "/analytics/lab?dataset=cross-sport&field=alt&other=value&group=MLB&order=asc&view=scatter&q=MLB&row=mlb&keep=present");
    const recoverable = vi.fn();
    let root: ReturnType<typeof hydrateRoot>;
    await act(async () => {
      root = hydrateRoot(container, <MeasurementLab data={fixture} />, { onRecoverableError: recoverable });
      await Promise.resolve();
    });

    expect(recoverable).not.toHaveBeenCalled();
    expect(window.location.search).toContain("keep=present");
    expect(window.history.state).toEqual({ next: "metadata" });
    act(() => root!.unmount());
    container.remove();
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

    expect(screen.getByRole("group", { name: /Alternate against Value/ })).toHaveAttribute("viewBox", "0 0 300 280");
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
