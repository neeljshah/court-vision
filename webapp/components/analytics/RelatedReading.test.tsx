import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/analytics/related", () => ({
  relatedReading: () => [{
    id: "observation-dependence", title: "Observation dependence", kind: "inspector",
    sport: "all", asOf: null, href: "/analytics/observation-dependence",
    purpose: "next question", prerequisite: "Read the effective sample size finding first.",
  }],
}));

import { RelatedReading } from "./RelatedReading";

describe("RelatedReading", () => {
  it("renders an inspector recommendation with its authored prerequisite", () => {
    render(<RelatedReading kind="analysis" id="calibration-by-game-checkpoint" />);
    expect(screen.getByText("Inspector")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Observation dependence/ })).toHaveAttribute("href", "/analytics/observation-dependence");
    expect(screen.getByText(/Prerequisite: Read the effective sample size finding first/)).toBeInTheDocument();
  });
});
