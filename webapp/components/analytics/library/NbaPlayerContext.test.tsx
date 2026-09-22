import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getNbaPlayerContextResearch } from "@/lib/analytics/researchNbaPlayerContext";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analysis = getNbaPlayerContextResearch()[0];
beforeEach(() => window.history.replaceState(null, "", `/analytics/research/${analysis.id}/`));
afterEach(() => vi.restoreAllMocks());

describe("NBA player on/off support", () => {
  it("exposes on-court support, exact season, and per-48 units in the inspector and CSV", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    const context = screen.getByRole("region", { name: "Source context" });
    expect(context).toHaveTextContent("On/off margin delta per 48: 2024-25, 2025-26");
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "on_off_minutes" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Zion Williamson" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 matching row; 1 contains on/off on-court minutes");
    fireEvent.click(screen.getByRole("button", { name: /^Inspect Zion Williamson/ }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    const inputs = within(selected).getByRole("region", { name: "Calculation inputs" });
    for (const [label, value] of [["On/off season", "2024-25"], ["On/off on-court minutes", "857.25"], ["On/off margin delta per 48", "15.772"]]) {
      const term = within(inputs).getByText(label, { selector: "dt" });
      expect(term.parentElement).toHaveTextContent(value);
    }
    expect(selected).toHaveTextContent("not necessarily the latest season played");
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const [dataset, rows] = exportCSV.mock.calls[0];
    expect(rows).toHaveLength(1);
    const csv = table.buildLabCSV(dataset, rows);
    expect(csv).toContain('"On/off on-court minutes (number; raw value)"');
    expect(csv).toContain(",857.25,");
    expect(csv).toContain("On/off season: 2024-25");
    expect(csv).toContain("off-court minutes are not published");
  });

  it("shows unavailable support for a player outside the published on/off lists", () => {
    const absent = analysis.rows.find(row => row.values.on_off_minutes === null)!;
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "on_off_minutes" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: absent.label } });
    expect(screen.getByRole("status")).toHaveTextContent("0 contain on/off on-court minutes");
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    fireEvent.click(screen.getByRole("button", { name: `Inspect ${absent.label}` }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    expect(selected).toHaveTextContent("On/off season: not published for this row");
    const inputs = within(selected).getByRole("region", { name: "Calculation inputs" });
    const term = within(inputs).getByText("On/off season", { selector: "dt" });
    expect(term.parentElement).toHaveTextContent("not published for this row");
  });
});
