import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/analytics/related", () => ({
  relatedReading: () => [{
    id: "observation-dependence", title: "Observation dependence", kind: "inspector",
    sport: "all", asOf: null, href: "/analytics/observation-dependence",
    purpose: "next question", prerequisite: "Read the effective sample size finding first.",
  }],
}));

import { RelatedReading, RelatedReadingLinks } from "./RelatedReading";

describe("RelatedReading", () => {
  it("renders an inspector recommendation with its authored prerequisite", () => {
    render(<RelatedReading kind="analysis" id="calibration-by-game-checkpoint" />);
    expect(screen.getByText("Inspector")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Observation dependence/ })).toHaveAttribute("href", "/analytics/observation-dependence");
    expect(screen.getByText(/Prerequisite: Read the effective sample size finding first/)).toBeInTheDocument();
  });

  it("keeps paper backlinks in the existing reading area", () => {
    render(<RelatedReading kind="module" id="blowout_dynamics" />);
    const papers = screen.getAllByRole("link").filter((link) => /\/analytics\/papers\//.test(link.getAttribute("href") || ""));
    expect(papers.length).toBeGreaterThan(0);
  });
});

describe("RelatedReadingLinks source dates", () => {
  it.each([
    { asOf: "not published", display: "not published" },
    { asOf: "not published; local 2025 pull", display: "not published; local 2025 pull" },
    { asOf: "2025-26 regular season (through 2026-04-12)", display: "2025-26 regular season (through 2026-04-12)" },
    { asOf: "2026-07-24T00:18:11.535624+00:00", display: "2026-07-24" },
    { asOf: "2026-05-21 16:05:11", display: "2026-05-21" },
    { asOf: "2026-07-24", display: "2026-07-24" },
    { asOf: "unknown", display: "unknown" },
    { asOf: null, display: "unrecorded" },
    { asOf: "", display: "unrecorded" },
  ])("shows $asOf as $display without inventing a date", ({ asOf, display }) => {
    render(<RelatedReadingLinks links={[{
      id: "date-example", title: "Date example", kind: "module", sport: "mlb",
      asOf, href: "/analytics/m/date-example/", purpose: "supporting source",
    }]} />);
    const link = screen.getByRole("link", { name: /Date example/ });
    expect(within(link).getByText(`MLB | as_of ${display}`, { exact: true })).toBeInTheDocument();
  });
});
