import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Home (/) deep-render tests -- the calibration scoreboard front page.
// Honesty rails: calibration/sharpness only; paper-only / no-edge sentences
// present; NO dollar figure, ROI, or P&L framing in the rendered output.
// Row-level scoreboard assertions live in home.scoreboard.test.tsx.

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("@/lib/atlas.server", () => ({ listPacks: () => [] }));

import Home from "../page";

describe("Home (/) -- the calibration scoreboard front page", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the hero headline and the no-edge framing", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toMatch(/calibrated sports predictor/i);
    expect(screen.getAllByText(/No edge is\s+claimed anywhere/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/calibration, not profit/i)).toBeTruthy();
    expect(screen.getByText(/What you will not find here/i)).toBeTruthy();
    expect(screen.getByText(/No ROI, profit, or betting-edge claim/i)).toBeTruthy();
  });

  it("renders the two primary CTAs linking evidence and analytics", () => {
    render(<Home />);
    expect(screen.getByRole("link", { name: /^read the evidence/i }).getAttribute("href")).toBe("/evidence");
    expect(screen.getByRole("link", { name: /open the analytics site/i }).getAttribute("href")).toBe("/analytics");
  });

  it("renders the honest reading and the confirmed-findings tile with the 0-of-60 qualifier", () => {
    render(<Home />);
    expect(screen.getByText(/match, do not beat/i)).toBeTruthy();
    expect(screen.getByText(/Both readings are true/i)).toBeTruthy();
    expect(
      screen.getByText(/confirmed ledger findings \(0 of 60 signal classes passed the gate\)/i),
    ).toBeTruthy();
  });

  it("links every live-app section", () => {
    render(<Home />);
    for (const label of ["games", "records", "paper trading", "system", "how it works", "methodology"]) {
      expect(screen.getAllByRole("link", { name: new RegExp(`^${label}$`, "i") }).length).toBeGreaterThan(0);
    }
  });

  it("renders NO dollar money-figure anywhere in the Home output", () => {
    const { container } = render(<Home />);
    const txt = container.textContent ?? "";
    // Ban a dollar VALUE (a $ followed by a number), plus ROI/P&L framing
    // outside the explicit "No ROI, ..." negation sentence.
    expect(/\$\s*\d/.test(txt)).toBe(false);
    expect(/\d\s*(dollars?|usd)\b/i.test(txt)).toBe(false);
    expect(/\bROI\b/.test(txt.replace(/No ROI, profit, or betting-edge claim/, ""))).toBe(false);
    expect(/\bP&L\b|\bPnL\b/i.test(txt)).toBe(false);
  });

  // Focus ring: primary CTAs and cards carry an explicit ring; every other
  // link is covered by the global :focus-visible rule in globals.css.
  it("primary CTAs and Door cards carry focus-visible ring classes", () => {
    render(<Home />);
    const ring = [
      screen.getByRole("link", { name: /^read the evidence/i }),
      screen.getByRole("link", { name: /open the analytics site/i }),
    ];
    for (const link of ring) {
      expect(link.className).toMatch(/focus-visible:outline-none/);
      expect(link.className).toMatch(/focus-visible:ring-2/);
      expect(link.className).toMatch(/focus-visible:ring-ring/);
    }
  });

  it("every other link is covered by the global :focus-visible rule", () => {
    const css = readFileSync(join(__dirname, "../../globals.css"), "utf8");
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:\s*2px solid/);
    render(<Home />);
    expect(screen.getAllByRole("link").length).toBeGreaterThan(8);
  });
});
