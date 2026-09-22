import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrierPhaseCoveragePanel } from "./BrierPhaseCoveragePanel";
import { buildBrierPhaseCoverage } from "@/lib/analytics/brierPhaseCoverage";
import source from "@/public/data/showcase/brier_skill_scores.json";

const coverage = buildBrierPhaseCoverage(source);

describe("Brier phase coverage panel", () => {
  it("shows the selected sport's source counts and accessible coverage graphic", () => {
    render(<BrierPhaseCoveragePanel coverage={coverage} sport="mlb" asOf="2026-09-16" />);
    const panel = screen.getByRole("article", { name: "MLB phase coverage" });
    expect(panel).toHaveTextContent("97.56%");
    expect(panel).toHaveTextContent("26,683");
    expect(panel).toHaveTextContent("668");
    expect(panel).toHaveTextContent("27,351");
    expect(within(panel).getByRole("img")).toHaveAccessibleName("MLB: 26,683 of 27,351 scored rows in published phases");
    expect(screen.queryByRole("article", { name: "International soccer phase coverage" })).not.toBeInTheDocument();
    expect(screen.getByText("Source as of 2026-09-16")).toBeInTheDocument();
  });

  it("keeps both sports separate when all populations are shown", () => {
    render(<BrierPhaseCoveragePanel coverage={coverage} />);
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(screen.getByRole("article", { name: "International soccer phase coverage" })).toHaveTextContent("79.32%");
    expect(screen.getAllByRole("img")).toHaveLength(2);
  });

  it("keeps invalid and zero-denominator coverage unavailable instead of drawing zero percent", () => {
    const invalid = [{ ...coverage[0], classified: null, outside: null, fraction: null, reason: "Phase counts are incomplete." }];
    const { rerender } = render(<BrierPhaseCoveragePanel coverage={invalid} />);
    expect(screen.getByText("Phase counts are incomplete.")).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable")).toHaveLength(3);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    rerender(<BrierPhaseCoveragePanel coverage={[{ ...coverage[0], total: 0, classified: 0, outside: 0, fraction: null, reason: "No scored rows." }]} />);
    expect(screen.queryByText("0.00%")).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("retains source operands, observation limits and the raw JSON link", () => {
    render(<BrierPhaseCoveragePanel coverage={coverage} sport="soccer_intl" />);
    expect(screen.getByText("sports.soccer_intl.grains.all.n")).toBeInTheDocument();
    expect(screen.getByText("sports.soccer_intl.grains.75-90+.n")).toBeInTheDocument();
    expect(screen.getByText(/not independent games/)).toBeInTheDocument();
    expect(screen.getByText(/publication date is not an observation window/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Inspect phase counts in the published source" })).toHaveAttribute("href", "/data/showcase/brier_skill_scores.json");
  });

  it("does not add a panel to other analyses or absent populations", () => {
    const { container, rerender } = render(<BrierPhaseCoveragePanel />);
    expect(container).toBeEmptyDOMElement();
    rerender(<BrierPhaseCoveragePanel coverage={coverage} sport="nba" />);
    expect(container).toBeEmptyDOMElement();
  });
});
