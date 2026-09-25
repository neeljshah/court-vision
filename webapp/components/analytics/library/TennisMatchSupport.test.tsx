import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ResearchDetail from "./ResearchDetail";
import { getTennisMatchSupportResearch } from "@/lib/analytics/researchTennisMatchSupport";
import * as table from "../lab/LabTable";

beforeEach(() => window.history.replaceState(null, "", "/analytics/research/tennis-clay-hard-match-support/"));
afterEach(() => vi.restoreAllMocks());

describe("tennis match support reader", () => {
  it("keeps the selected windows in a source-order table and exposes counts", () => {
    render(<ResearchDetail analysis={getTennisMatchSupportResearch()[0]} related={[]} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("20 matching rows");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Adrian Mannarino" } });
    fireEvent.click(screen.getByRole("button", { name: "Inspect Adrian Mannarino (career)" }));
    const details = screen.getByRole("region", { name: "Selected measurement" });
    expect(within(details).getByText("13.26%")).toBeInTheDocument();
    expect(within(details).getByText("-28.23 pp")).toBeInTheDocument();
    expect(details).toHaveTextContent("59");
    expect(details).toHaveTextContent("386");
    expect(screen.queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
  });

  it("exports separate overlapping-window rows with published gaps and paths", () => {
    const analysis = getTennisMatchSupportResearch()[0];
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Sebastian Baez" } });
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const rows = exportCSV.mock.calls[0][1];
    expect(rows.map(row => row.label)).toEqual(["Sebastian Baez (career)", "Sebastian Baez (recent form)"]);
    expect(rows.map(row => row.values.clay_minus_hard)).toEqual([0.3396, 0.3169]);
    const csv = table.buildLabCSV(analysis, rows);
    expect(csv).toContain("combos.atp_career.clay_hard_gap.most_clay_favoring[1].clay_n");
    expect(csv).toContain("combos.atp_recent_form.clay_hard_gap.most_clay_favoring[1].hard_n");
    expect(csv).toContain("2015-2025");
    expect(csv).toContain("2023-01-01");
    expect(analysis.asOf).toBeUndefined();
  });
});
