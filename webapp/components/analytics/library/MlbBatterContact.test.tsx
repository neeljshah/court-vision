import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getMlbBatterContactResearch } from "@/lib/analytics/researchMlbBatterContact";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analysis = getMlbBatterContactResearch()[0];
beforeEach(() => window.history.replaceState(null, "", `/analytics/research/${analysis.id}/`));
afterEach(() => vi.restoreAllMocks());

describe("Published MLB exit-velocity investigation", () => {
  it("shows the signed difference beside its operands and sample counts, including in CSV", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Aaron Judge" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 matching row;");
    fireEvent.click(screen.getByRole("button", { name: /^Inspect Aaron Judge:/ }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    for (const value of ["21.9 mph", "109.5 mph", "87.6 mph", "698", "2,715"]) {
      expect(within(selected).getByText(value)).toBeVisible();
    }
    expect(screen.getByText(analysis.scope)).toBeVisible();
    expect(screen.getByText(analysis.caveat)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const [dataset, rows] = exportCSV.mock.calls[0];
    expect(rows).toHaveLength(1);
    expect(rows[0].values).toMatchObject({ exit_velo_p90: 109.5, avg_exit_velo: 87.6, recorded_exit_velocities: 698, pitches_faced: 2715 });
    const csv = table.buildLabCSV(dataset, rows);
    for (const text of ["Aaron Judge", "atlas_mlb_batters_manifest", analysis.scope, analysis.caveat, analysis.formula]) expect(csv).toContain(text);
    expect(screen.getByRole("link", { name: /Published source JSON/ })).toHaveAttribute("href", "/data/showcase/atlas_mlb_batters_manifest.json");
  });

  it("restores a shared batter table and resets to the full published population", () => {
    window.history.replaceState(null, "", `?q=Luis+Arraez&view=table&metric=avg_exit_velo&utm_source=shared`);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("textbox", { name: "Search analysis rows" })).toHaveValue("Luis Arraez");
    expect(screen.getByRole("status")).toHaveTextContent("1 matching row;");
    const measurements = screen.getByRole("region", { name: "Scrollable measurements" });
    expect(within(measurements).getByText("14.2 mph")).toBeVisible();
    expect(within(measurements).getByText("95.4 mph")).toBeVisible();
    expect(within(measurements).getByText("81.2 mph")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(screen.getByRole("status")).toHaveTextContent("485 matching rows;");
    expect(window.location.search).toBe("?utm_source=shared");
  });

  it("returns keyboard focus to the scatter point after closing its measurement", () => {
    window.history.replaceState(null, "", "?q=Aaron+Judge&view=scatter");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    const point = screen.getByRole("button", { name: /^Inspect Aaron Judge:/ });
    point.focus();
    fireEvent.keyDown(point, { key: "Enter" });
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    expect(selected).toHaveFocus();
    fireEvent.keyDown(selected, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Selected measurement" })).not.toBeInTheDocument();
    expect(point).toHaveFocus();
    expect(point).toHaveAttribute("tabindex", "0");
  });
});
