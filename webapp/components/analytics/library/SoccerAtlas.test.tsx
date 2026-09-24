import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getAtlasPackResearch } from "@/lib/analytics/researchAtlasPacks";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analysis = getAtlasPackResearch().find(item => item.id === "soccer-team-atlas-measurements")!;
const como = analysis.rows.find(row => row.label === "Como")!;
beforeEach(() => window.history.replaceState(null, "", `/analytics/research/${analysis.id}/`));
afterEach(() => vi.restoreAllMocks());

describe("Soccer atlas population context", () => {
  it("keeps source-order rows and their scalar values available for inspection and export", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Order" })).toHaveTextContent("Published source order");
    expect(screen.getByRole("region", { name: "Population comparison notice" })).toHaveTextContent("six divisions");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("187 matching rows");
    const rows = within(screen.getByRole("region", { name: "Scrollable measurements" })).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Ajaccio");
    expect(rows[2]).toHaveTextContent("Ajaccio GFCO");
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Como" } });
    fireEvent.click(screen.getByRole("button", { name: "Inspect Como" }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    const awayLabel = analysis.fields.find(field => field.key === "clean_sheet_rate_away")!.label;
    expect(within(within(selected).getByText(awayLabel).parentElement!).getByText("70%")).toBeVisible();
    expect(within(selected).queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const [dataset, exportedRows] = exportCSV.mock.calls[0];
    expect(exportedRows).toEqual([como]);
    expect(exportedRows[0].values.clean_sheet_rate_away).toBe(0.7);
    const csv = table.buildLabCSV(dataset, exportedRows);
    for (const text of ["Como", "atlas_soccer_manifest", "2026-07-18", "six divisions", "league or match dates", como.sourcePaths![0], como.note!]) expect(csv).toContain(text);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "no such soccer team" } });
    expect(screen.getByRole("button", { name: "Export CSV" })).toBeDisabled();
  });

  it("restores a selected team from an old chart link without restoring pooled statistics", () => {
    window.history.replaceState(null, "", `?q=Como&population=sport%3Dsoccer&view=distribution&row=${como.id}&utm_source=shared`);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("Como");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Measurement distribution" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    expect(screen.getByRole("region", { name: "Scrollable measurements" })).toHaveTextContent("Como");
    expect(new URLSearchParams(window.location.search).get("utm_source")).toBe("shared");
  });
});
