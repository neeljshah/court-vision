import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { establishedDatasets } from "@/lib/analytics/labEstablished";
import MeasurementLab from "./MeasurementLab";
import * as table from "./LabTable";

const dataset = establishedDatasets().find(item => item.id === "lineup-synergy")!;
const data = { datasets: [dataset], novel: [] };
beforeEach(() => window.history.replaceState(null, "", "/analytics/lab/?dataset=lineup-synergy&field=minutes_per_game"));
afterEach(() => vi.restoreAllMocks());

describe("lineup support and measurement units", () => {
  it("finds a lineup by a full player name and exposes per-minute units and source support", () => {
    render(<MeasurementLab data={data} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Primary measurement" })).toHaveValue("minutes_per_game");
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "Jaren Jackson Jr." } });
    const measurements = screen.getByRole("table");
    expect(within(measurements).getByRole("columnheader", { name: "Observed net points / 48 min" })).toBeInTheDocument();
    expect(within(measurements).getByRole("columnheader", { name: "Minutes per recorded game" })).toBeInTheDocument();
    expect(within(measurements).getByRole("cell", { name: "8.87" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: `Inspect ${dataset.rows[0].label}` }));
    const details = screen.getByRole("region", { name: "Selected measurement" });
    expect(details).toHaveTextContent("Memphis");
    expect(details).toHaveTextContent("Jaren Jackson Jr.");
    expect(details).toHaveTextContent("Jaylen Wells");
    expect(details).toHaveTextContent("top[0]");
    expect(details).toHaveTextContent("221.8");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Rank order" })).toBeDisabled();
    fireEvent.keyDown(details, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Selected measurement" })).not.toBeInTheDocument();
  });

  it("exports original observations and full roster provenance alongside the derived support ratio", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<MeasurementLab data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    const rows = exportCSV.mock.calls[0][1];
    expect(rows).toHaveLength(23);
    expect(rows[0].values.minutes_per_game).toBe(221.8 / 25);
    expect(rows[0].values.synergy_residual).toBe(24.32);
    expect(rows[15].values.minutes_per_game).toBe(136.9 / 13);
    const csv = table.buildLabCSV(dataset, rows);
    expect(csv).toContain("Minutes per recorded game");
    expect(csv).toContain("Jaren Jackson Jr.");
    expect(csv).toContain("bottom[0]");
    expect(csv).toContain("102");
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "Jerami Grant" } });
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    expect(exportCSV.mock.calls[1][1].every(row => row.note?.includes("Jerami Grant"))).toBe(true);
    expect(exportCSV.mock.calls[1][1].length).toBeGreaterThan(0);
    expect(exportCSV.mock.calls[1][1].length).toBeLessThan(23);
  });
});
