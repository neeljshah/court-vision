import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { multisportResearch } from "@/lib/analytics/researchMultisport";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analysis = multisportResearch().find(item => item.id === "mlb-pitch-mix-concentration")!;
beforeEach(() => window.history.replaceState(null, "", `/analytics/research/${analysis.id}/`));
afterEach(() => vi.restoreAllMocks());

describe("Pitch mix count context", () => {
  it("shows the within-type denominator, count label and distinct dates in the inspector and CSV", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    const context = screen.getByRole("region", { name: "Source context" });
    expect(context).toHaveTextContent("not published; local 2025 pull");
    expect(context).toHaveTextContent("2025-09-28");
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "two_strike_share" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "FF" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 matching row; 1 contains two-strike share within pitch type");
    fireEvent.click(screen.getByRole("button", { name: /^Inspect FF/ }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    const inputs = within(selected).getByRole("region", { name: "Calculation inputs" });
    for (const [label, value] of [["Two-strike share within pitch type", "30.03%"], ["Peak ball-strike count", "0-0"], ["Pitches of this type", "220,235"]]) {
      const term = within(inputs).getByText(label, { selector: "dt" });
      expect(term.parentElement).toHaveTextContent(value);
    }
    expect(selected).toHaveTextContent("League pitch share denominator: 693,037 pitches");
    expect(selected).toHaveTextContent("Count shares are within pitch type FF (n=220,235)");
    expect(inputs).toHaveTextContent("league_share (31.78%) = published pct / 100");
    expect(inputs).toHaveTextContent("first_pitch_share (26.44%) = count_state_pct[0-0] / 100");
    expect(inputs).toHaveTextContent("two_strike_share (30.03%) = sum");
    expect(inputs).toHaveTextContent("peak_count_share (26.44%) = max");
    expect(inputs).not.toHaveTextContent("two_strike_share (31.78%)");
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const [dataset, rows] = exportCSV.mock.calls[0];
    expect(rows).toHaveLength(1);
    const csv = table.buildLabCSV(dataset, rows);
    expect(csv).toContain("Two-strike share within pitch type (percent; raw value)");
    expect(csv).toContain("Peak count: 0-0");
    expect(csv).toContain("Atlas as of 2025-09-28; Statcast local 2025 pull");
    expect(csv).toContain('"Sources (JSON)"');
    expect(csv).toContain('""id"":""statcast_showcase""');
    expect(csv).toContain('""id"":""atlas_mlb_pitch_manifest""');
    expect(csv).toContain('""asOf"":""not published; local 2025 pull""');
    expect(csv).toContain('""asOf"":""2025-09-28""');
    expect(csv).toContain('""sourceId"":""atlas_mlb_pitch_manifest""');
    expect(csv).toContain("atlas_mlb_pitch_manifest.entries[entity=pitch_type:FF].key_numbers.count_state_pct");
    expect(csv).toContain('""peak_count"":""0-0""');
    expect(screen.getByText(/structured provenance uses JSON cells/)).toBeVisible();
    expect(rows[0].values.two_strike_share).toBeCloseTo(0.3003, 10);
  });

  it("keeps a sparse incomplete category in the table without inventing its peak", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Measurement" }), { target: { value: "peak_count_share" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "SC (n=7)" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 matching row; 0 contain peak count share within pitch type");
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    fireEvent.click(screen.getByRole("button", { name: "Inspect SC", exact: true }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    expect(selected).toHaveTextContent("Peak count: unavailable");
    expect(selected).toHaveTextContent("5/12 count shares published");
    expect(selected).toHaveTextContent("type SC (n=7)");
    expect(selected).toHaveTextContent("omitted counts remain unavailable");
  });
});
