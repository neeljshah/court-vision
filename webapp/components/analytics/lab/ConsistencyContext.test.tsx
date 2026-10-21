import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { establishedDatasets } from "@/lib/analytics/labEstablished";
import MeasurementLab from "./MeasurementLab";
import * as table from "./LabTable";

const dataset = establishedDatasets().find(item => item.id === "nba-consistency")!;
const data = { datasets: [dataset], novel: [] };
beforeEach(() => window.history.replaceState(null, "", "/analytics/lab/?dataset=nba-consistency&field=shrink_weight&view=table"));
afterEach(() => vi.restoreAllMocks());

describe("consistency estimate context", () => {
  it("shows the published blend weight and qualifying-game definition beside unchanged variability", () => {
    render(<MeasurementLab data={data} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Primary measurement" })).toHaveValue("shrink_weight");
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "Luka Doncic" } });
    const measurements = screen.getByRole("table");
    expect(within(measurements).getByRole("columnheader", { name: "Qualifying game appearances" })).toBeInTheDocument();
    expect(within(measurements).getByRole("cell", { name: "90.2%" })).toBeInTheDocument();
    expect(within(measurements).getByRole("cell", { name: "0.3448" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect Luka Doncic" }));
    const details = screen.getByRole("region", { name: "Selected measurement" });
    expect(details).toHaveTextContent("most_consistent_top15[0]");
    expect(details).toHaveTextContent("1629029");
    expect(details).toHaveTextContent("184");
    expect(details).toHaveTextContent(/confidence/i);
    expect(screen.getByRole("region", { name: "Measurement summary" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Rank order" })).not.toBeDisabled();
    expect(screen.getAllByText(/2026-04-12/).length).toBeGreaterThan(0);
    const definition = screen.getByRole("region", { name: "Published definition" });
    expect(within(definition).getByText("Sport").nextElementSibling).toHaveTextContent("NBA");
    expect(within(definition).getByText("Population").nextElementSibling).toHaveTextContent("579 players meeting the floor of 807 source players; games at or above 10 minutes; at least 15 qualifying appearances");
    expect(within(definition).getByText("Observation window").nextElementSibling).toHaveTextContent("2023-24, 2024-25, 2025-26 pooled; as of 2026-04-12");
  });

  it("preserves raw source weights and provenance in full and filtered exports", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<MeasurementLab data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    const rows = exportCSV.mock.calls[0][1];
    expect(rows).toHaveLength(30);
    expect(rows[0].values.shrink_weight).toBe(0.902);
    expect(rows[15].values.shrink_weight).toBe(0.565);
    expect(rows[24].values.shrink_weight).toBe(0.429);
    const csv = table.buildLabCSV(dataset, rows);
    expect(csv).toContain("Player-data blend weight (percent; raw value)");
    expect(csv).toContain("least_consistent_top15[9]");
    expect(csv).toContain("2026-04-12");
    expect(csv).toContain("579");
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "Moses Brown" } });
    expect(within(screen.getByRole("table")).getByRole("cell", { name: "42.9%" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    expect(exportCSV.mock.calls[1][1].map(row => row.label)).toEqual(["Moses Brown"]);
    expect(exportCSV.mock.calls[1][1][0].values.games).toBe(15);
  });
});
