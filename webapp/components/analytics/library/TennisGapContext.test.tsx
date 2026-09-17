import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";
import { TennisGapContext } from "./TennisGapContext";

const analysis = (id: string, count = 2) => ({ id, rows: Array.from({ length: count }, (_, index) => ({ id: String(index) })) }) as ResearchAnalysis;

describe("TennisGapContext", () => {
  it("states the clay definition, overlapping windows, and unavailable exact counts", () => {
    render(<TennisGapContext analysis={analysis("tennis-clay-gap-window-shift")} />);
    expect(screen.getByLabelText("Gap definition")).toHaveTextContent("Clay win rate minus hard-court win rate");
    expect(screen.getByLabelText("Published windows")).toHaveTextContent("not lifetime career");
    expect(screen.getByLabelText("Published windows")).toHaveTextContent("overlaps the source corpus");
    expect(screen.getByLabelText("Row comparison")).toHaveTextContent("2 qualified players; exact match counts are unavailable");
  });

  it("keeps grass's pooled baseline and sibling link accessible", () => {
    render(<TennisGapContext analysis={analysis("tennis-grass-gap-window-shift", 1)} />);
    expect(screen.getByLabelText("Gap definition")).toHaveTextContent("Grass win rate minus pooled overall win rate");
    expect(screen.getByLabelText("Gap definition")).toHaveTextContent("includes grass matches");
    expect(screen.getByRole("link", { name: "View clay versus hard-court gap" })).toHaveAttribute("href", "/analytics/research/tennis-clay-gap-window-shift");
  });

  it("does not render for other analyses", () => {
    const { container } = render(<TennisGapContext analysis={analysis("tennis-hard-recent-career-shift")} />);
    expect(container).toBeEmptyDOMElement();
  });
});
