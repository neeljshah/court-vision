import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { analysisDestinations } from "@/lib/analytics/analysisDestinations";
import { bestPaperForInspector, readingEntries } from "@/lib/analytics/related.server";
import { InspectorReadingTrail } from "./InspectorReadingTrail";

const trails = [
  ["calibration", "/analytics/findings/reliability/", "/analytics/observation-dependence"],
  ["state-reliability", "/analytics/calibration", "/analytics/residual-anatomy"],
  ["pitch-sequencing", "/analytics/research/mlb-pitch-mix-concentration/", "/analytics/count-context"],
  ["count-context", "/analytics/research/mlb-count-contrast/", "/analytics/pitch-sequencing"],
  ["score-decomposition", "/analytics/calibration", "/analytics/cross-sport-comparability"],
  ["observation-dependence", "/analytics/findings/effective-sample-size/", "/analytics/state-reliability"],
  ["residual-anatomy", "/analytics/observation-dependence", "/analytics/score-decomposition"],
  ["blowout-timing", "/analytics/research/comeback-rates-deficit-time/", "/analytics/state-contrasts"],
  ["state-contrasts", "/analytics/blowout-timing", "/analytics/observation-dependence"],
  ["cross-sport-comparability", "/analytics/calibration", "/analytics/calibration"],
] as const;

describe("InspectorReadingTrail", () => {
  it.each(trails)("follows the authored reading trail for %s", (id, prerequisiteHref, nextHref) => {
    render(<InspectorReadingTrail id={id} />);
    const trail = screen.getByRole("region", { name: "Reading trail" });
    const readFirst = within(trail).getByText(/Read first:/).closest("p");
    const nextQuestion = within(trail).getByText(/Next question:/).closest("p");
    expect(readFirst).not.toBeNull();
    expect(nextQuestion).not.toBeNull();
    const norm = (href: string) => href.replace(/\/$/, "");
    expect(norm(within(readFirst!).getByRole("link").getAttribute("href") || "")).toBe(norm(prerequisiteHref));
    expect(norm(within(nextQuestion!).getByRole("link").getAttribute("href") || "")).toBe(norm(nextHref));
    const paper = bestPaperForInspector(id);
    const analysisLines = within(trail).getAllByText((_, element) => element?.tagName === "P" && element.textContent?.startsWith("Read the analysis:") === true);
    expect(analysisLines).toHaveLength(paper ? 1 : 0);
    if (paper) expect(within(analysisLines[0].closest("p")!).getByRole("link")).toHaveAttribute("href", expect.stringMatching(new RegExp(`/analytics/papers/${paper.id}/?$`)));
    const routes = new Set([...analysisDestinations.map((destination) => norm(destination.route)), ...readingEntries().map((entry) => norm(entry.href))]);
    for (const link of Array.from(trail.querySelectorAll("a"))) expect({ href: link.getAttribute("href"), known: routes.has(norm(link.getAttribute("href") || "")) }).toEqual({ href: link.getAttribute("href"), known: true });
  });

  it("mounts the integrity notice only for an affected inspector", () => {
    const { rerender } = render(<InspectorReadingTrail id="state-reliability" />);
    expect(screen.getAllByRole("complementary", { name: "Data integrity" })[0]).toHaveTextContent("state_conditioned_calibration");
    rerender(<InspectorReadingTrail id="count-context" />);
    expect(screen.queryByRole("complementary", { name: "Data integrity" })).not.toBeInTheDocument();
  });
});
