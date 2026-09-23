import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { getMultisportDepthResearch } from "@/lib/analytics/researchMultisportDepth";
import { buildTennisSurfaceFolds } from "@/lib/analytics/tennisSurfaceFolds";
import ResearchDetail from "./ResearchDetail";
import { TennisSurfaceFoldPanel } from "./TennisSurfaceFoldPanel";

const analysis = getMultisportDepthResearch().find(item => item.id === "tennis-surface-prior-brier-delta")!;
beforeEach(() => window.history.replaceState(null, "", `/analytics/research/${analysis.id}/`));

describe("tennis surface-prior fold drilldown", () => {
  it("opens all six source rows in separate tour tables with exact scores and provenance", () => {
    render(<ResearchDetail analysis={analysis} related={[]} />);
    fireEvent.click(screen.getByText("Inspect 6 held-out fold results"));
    const panel = screen.getByRole("region", { name: "Published tennis surface-prior folds" });
    expect(panel).toBeVisible();
    const atp = within(panel).getByRole("table", { name: "ATP held-out folds: published Brier scores and test-state counts" });
    const wta = within(panel).getByRole("table", { name: "WTA held-out folds: published Brier scores and test-state counts" });
    expect(within(atp).getAllByRole("row")).toHaveLength(4);
    expect(within(wta).getAllByRole("row")).toHaveLength(4);
    expect(within(atp).getAllByText("8,780")).toHaveLength(3);
    expect(within(atp).getByText("0.166648")).toBeVisible();
    expect(within(atp).getByText("+0.000096")).toBeVisible();
    expect(within(wta).getByText("2,645")).toBeVisible();
    expect(within(wta).getByText("+0.003442")).toBeVisible();
    expect(panel).toHaveTextContent("calendar test dates are not published");
    expect(panel).toHaveTextContent("comparison was rejected");
    fireEvent.click(within(atp).getAllByText("Source path")[0]);
    expect(within(atp).getByText("ingame_surface_context.tours.atp.n_folds[0]")).toBeVisible();
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "WTA" } });
    expect(screen.getByRole("status")).toHaveTextContent("1 matching row");
    expect(within(panel).getAllByRole("table")).toHaveLength(2);
  });

  it("keeps zero, missing support, and negative differences distinct", () => {
    const groups = buildTennisSurfaceFolds({ atp: { n_folds: [
      { fold: 0, n_test: 2, brier_h0: 0, brier_h1: 0 },
      { fold: 1, n_test: null, brier_h0: 0.2, brier_h1: 0.1 },
      { fold: 2, n_test: 3, brier_h0: null, brier_h1: 0.1 },
    ] } });
    render(<TennisSurfaceFoldPanel groups={groups} />);
    fireEvent.click(screen.getByText("Inspect 3 held-out fold results"));
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(within(rows[0]).getAllByText("0.000000")).toHaveLength(3);
    expect(within(rows[1]).getByText("Unavailable")).toBeVisible();
    expect(within(rows[1]).getByText("-0.100000")).toBeVisible();
    expect(within(rows[2]).getAllByText("Unavailable")).toHaveLength(2);
  });

  it("renders no unrelated panel and explains a published tour without fold rows", () => {
    const { rerender, container } = render(<TennisSurfaceFoldPanel />);
    expect(container).toBeEmptyDOMElement();
    rerender(<TennisSurfaceFoldPanel groups={[{ tour: "atp", rows: [] }]} />);
    fireEvent.click(screen.getByText("Inspect 0 held-out fold results"));
    expect(screen.getByText("No fold rows are published for this tour.")).toBeVisible();
  });
});
