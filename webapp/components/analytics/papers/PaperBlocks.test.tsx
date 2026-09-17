import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/analytics/papers.server", () => ({
  paperFigure: () => ({ id: "fixture", title: "Fixture chart", chartSrc: "/chart.png", source: "fixture.json", asOf: "2026-09-15", dateKind: "snapshot", fallback: { headers: [], rows: [] } }),
}));
vi.mock("@/lib/analytics/publishedChartPresentation", () => ({
  getPublishedChartPresentation: () => ({ approved: true, reason: "" }),
}));
import { PaperBlockView } from "./PaperBlocks";

describe("PaperBlockView", () => {
  it("names table regions with the horizontal-scroll instruction and renders the phone hint", () => {
    render(
      <PaperBlockView
        block={{
          type: "table",
          caption: "Published calibration table",
          columns: ["Bin", "Observed"],
          rows: [["0.4 to 0.5", "0.43"]],
        }}
      />,
    );

    expect(screen.getByRole("region", { name: /Published calibration table, scroll horizontally for all columns$/ })).toBeInTheDocument();
    expect(screen.getByText("Scroll horizontally to see all columns.")).toHaveClass("paper-scroll-hint");
  });

  it("forwards resolved artifact date kind to the figure receipt", () => {
    render(<PaperBlockView block={{ type: "figure", module: "fixture", caption: "Published fixture chart" }} />);
    expect(screen.getByText("Snapshot generated 2026-09-15")).toBeInTheDocument();
  });
});
