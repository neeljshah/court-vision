import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getTennisWindowResearch } from "@/lib/analytics/researchTennisWindows";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analyses = getTennisWindowResearch();
beforeEach(() => window.history.replaceState(null, "", "/analytics/research/tennis-hard-recent-career-shift/"));
afterEach(() => vi.restoreAllMocks());

describe("Published tennis window investigation", () => {
  it("displays a signed percentage-point gap once and exports its two original rate operands", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analyses[0]} related={[]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Andy Murray" } });
    fireEvent.click(screen.getByRole("button", { name: /^Inspect Andy Murray/ }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    expect(within(selected).getByText("-18.54 pp")).toBeInTheDocument();
    expect(within(selected).getByText("48.78%")).toBeInTheDocument();
    expect(within(selected).getByText("67.32%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const [dataset, rows] = exportCSV.mock.calls[0];
    expect(dataset.source).toBe("atlas_tennis_manifest");
    expect(dataset.caveat).toMatch(/subset|overlap/i);
    expect(rows).toHaveLength(1);
    expect(rows[0].values.recent_minus_career).toBeCloseTo(-.1854, 10);
    expect(rows[0].values).toMatchObject({ recent_rate: .4878, career_rate: .6732 });
  });

  it("keeps the sparse grass population and its limits visible", () => {
    render(<ResearchDetail analysis={analyses[2]} related={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent("3 matching rows");
    expect(screen.getByText(analyses[2].scope)).toBeVisible();
    expect(screen.getByText(analyses[2].caveat)).toBeVisible();
    expect(screen.getByRole("link", { name: /Published source JSON/ })).toHaveAttribute("href", "/data/showcase/atlas_tennis_manifest.json");
  });
});
