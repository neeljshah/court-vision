import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ResearchDetail from "./ResearchDetail";
import { getMlbPlatoonSupportResearch } from "@/lib/analytics/researchMlbPlatoonSupport";
import * as table from "../lab/LabTable";

beforeEach(() => window.history.replaceState(null, "", "/analytics/research/mlb-platoon-support-balance/"));
afterEach(() => vi.restoreAllMocks());

describe("MLB platoon support reader", () => {
  it("shows the published selection as a table without a full-population ranking", () => {
    render(<ResearchDetail analysis={getMlbPlatoonSupportResearch()[0]} related={[]} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("15 matching rows");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Mitch Garver" } });
    fireEvent.click(screen.getByRole("button", { name: "Inspect Mitch Garver" }));
    const details = screen.getByRole("region", { name: "Selected measurement" });
    expect(within(details).getByText("15.2 pp")).toBeInTheDocument();
    expect(details).toHaveTextContent("148");
    expect(details).toHaveTextContent("413");
    expect(screen.queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
  });

  it("exports the searched record with raw gap, support balance and source paths", () => {
    const analysis = getMlbPlatoonSupportResearch()[0];
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Mitch Garver" } });
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const rows = exportCSV.mock.calls[0][1];
    expect(rows).toHaveLength(1);
    expect(rows[0].values.platoon_delta).toBe(0.152);
    expect(rows[0].values.smaller_side_support_share).toBeCloseTo(148 / 561, 12);
    const csv = table.buildLabCSV(analysis, rows);
    expect(csv).toContain("platoon_splits.top[0].pa_vs_l");
    expect(csv).toContain("platoon_splits.top[0].pa_vs_r");
    expect(csv).toContain("2022-2023");
  });
});
