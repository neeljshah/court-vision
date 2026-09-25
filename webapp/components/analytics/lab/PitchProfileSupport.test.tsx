import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { establishedDatasets } from "@/lib/analytics/labEstablished";
import MeasurementLab from "./MeasurementLab";
import * as table from "./LabTable";

const dataset = establishedDatasets().find(item => item.id === "pitch-profiles")!;
const data = { datasets: [dataset], novel: [] };
beforeEach(() => window.history.replaceState(null, "", "/analytics/lab/?dataset=pitch-profiles&field=velocity_span"));
afterEach(() => vi.restoreAllMocks());

describe("pitch-profile velocity support", () => {
  it("shows the span and recorded-speed coverage with their source notes", () => {
    render(<MeasurementLab data={data} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "FF" } });
    const measurements = screen.getByRole("table");
    expect(within(measurements).getByRole("cell", { name: "6.4 mph" })).toBeInTheDocument();
    expect(within(measurements).getByRole("cell", { name: "99.999%" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect FF" }));
    const details = screen.getByRole("region", { name: "Selected measurement" });
    expect(details).toHaveTextContent("pitch_type_distribution[0]");
    expect(details).toHaveTextContent("velo_percentiles_by_pitch_type[0]");
    expect(details).toHaveTextContent(/round/i);
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
  });

  it("keeps omitted velocity groups unavailable and exports the original denominators", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<MeasurementLab data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    const rows = exportCSV.mock.calls[0][1];
    expect(rows).toHaveLength(19);
    const ff = rows.find(row => row.label === "FF")!;
    expect(ff.values.velocity_span).toBeCloseTo(6.4);
    expect(ff.values.velocity_coverage).toBe(220233 / 220235);
    expect(ff.values.mix_n).toBe(220235);
    expect(ff.values.velocity_n).toBe(220233);
    for (const label of ["UNK", "UN", "SC"]) {
      const row = rows.find(item => item.label === label)!;
      expect(row.values.velocity_span).toBeNull();
      expect(row.values.velocity_coverage).toBeNull();
      expect(row.values.velocity_n).toBeNull();
    }
    const csv = table.buildLabCSV(dataset, rows);
    expect(csv).toContain(String(220233 / 220235));
    expect(csv).toContain("velo_percentiles_by_pitch_type[0]");
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "UNK" } });
    expect(within(screen.getByRole("table")).getAllByRole("cell", { name: "Unavailable" })).toHaveLength(6);
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    expect(exportCSV.mock.calls[1][1].map(row => row.label)).toEqual(["UNK"]);
  });
});
