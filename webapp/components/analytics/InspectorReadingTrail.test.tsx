import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { analysisDestinations } from "@/lib/analytics/analysisDestinations";
import { readingEntries } from "@/lib/analytics/related";
import { InspectorReadingTrail } from "./InspectorReadingTrail";

describe("InspectorReadingTrail", () => {
  it("links state reliability to its prerequisite, next inspector, and three related readings", () => {
    render(<InspectorReadingTrail id="state-reliability" />);
    const trail = screen.getByRole("region", { name: "Reading trail" });
    expect(within(trail).getByText(/Read first:/)).toBeInTheDocument();
    expect(within(trail).getByRole("link", { name: /Read the calibration reliability bins/i })).toHaveAttribute("href", expect.stringMatching(/^\/analytics\/calibration\/?$/));
    expect(within(trail).getByRole("link", { name: /Which time and probability cells/i })).toHaveAttribute("href", expect.stringMatching(/^\/analytics\/score\-decomposition\/?$/));
    expect(trail.querySelectorAll(".related-reading-card").length).toBeLessThanOrEqual(3);
    const norm = (href: string) => href.replace(/\/$/, "");
    const routes = new Set([...analysisDestinations.map((destination) => norm(destination.route)), ...readingEntries().map((entry) => norm(entry.href))]);
    for (const link of Array.from(trail.querySelectorAll("a"))) expect({ href: link.getAttribute("href"), known: routes.has(norm(link.getAttribute("href") || "")) }).toEqual({ href: link.getAttribute("href"), known: true });
  });
});
