import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { establishedDatasets } from "@/lib/analytics/labEstablished";
import MeasurementLab from "./MeasurementLab";
import * as table from "./LabTable";

const dataset = establishedDatasets().find(item => item.id === "soccer-home-advantage")!;
const data = { datasets: [dataset], novel: [] };
beforeEach(() => window.history.replaceState(null, "", "/analytics/lab/?dataset=soccer-home-advantage&allCohorts=true&field=neutral_match_share"));
afterEach(() => vi.restoreAllMocks());

describe("soccer era venue composition", () => {
  it("shows both era shares and source-rounded gaps without pooling the eras", () => {
    render(<MeasurementLab data={data} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Rank order" })).toBeDisabled();
    const measurements = screen.getByRole("table");
    expect(within(measurements).getAllByRole("button", { name: /^Inspect / }).map(button => button.getAttribute("aria-label")))
      .toEqual(["Inspect pre-2000", "Inspect 2000+"]);
    for (const value of ["24.22%", "28.58%", "0.6743", "0.6745", "0.2187", "0.4985", "18,235", "5,827", "18,115", "7,248"])
      expect(within(measurements).getByRole("cell", { name: value })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect 2000+" }));
    const details = screen.getByRole("region", { name: "Selected measurement" });
    expect(details).toHaveTextContent("28.58%");
    expect(details).toHaveTextContent("by_era[1]");
    expect(within(details).queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
  });

  it("exports full-precision shares, separate era definitions, and the original counts", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<MeasurementLab data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    const rows = exportCSV.mock.calls[0][1];
    expect(rows.map(row => row.values.neutral_match_share)).toEqual([5827 / 24062, 7248 / 25363]);
    expect(rows.map(row => row.definition?.observationWindow)).toEqual(["pre-2000", "2000+"]);
    const csv = table.buildLabCSV(dataset, rows);
    for (const value of ["0.2187", "0.4985", "18235", "5827", "18115", "7248", "by_era[0]", "by_era[1]", "1872-11-30", "2026-06-16", "Row definition (JSON)"])
      expect(csv).toContain(value);
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "2000+" } });
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    expect(exportCSV.mock.calls[1][1].map(row => row.label)).toEqual(["2000+"]);
  });
});
