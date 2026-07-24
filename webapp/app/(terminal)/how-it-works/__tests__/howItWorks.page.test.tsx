import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// How-it-works (/how-it-works) full-page render test.
//
// Asserts the page composes its five honest sections together and carries the
// page-level "Calibration, not a market edge" disclaimer + the no-$ framing.
// The client sections fetch real endpoints; we stub those so the page settles
// into the HONEST default (parity unknown, self-improve READY-inert, no live
// example) without a network. NO $ figure may appear in the whole page.

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import * as apiMod from "@/lib/api";
import HowItWorksPage from "../page";

describe("How-it-works page -- composes the honest sections", () => {
  afterEach(() => vi.restoreAllMocks());

  function stubHonestDefault() {
    vi.spyOn(apiMod, "getParityHeadline").mockResolvedValue({
      green: true,
      nSports: 4,
      reason: "ok",
    } as never);
    vi.spyOn(apiMod, "getProductStatus").mockResolvedValue({
      selfImprove: "READY_INERT",
    } as never);
    // LiveExample reads api.getPredict -> honest empty (no fabricated game).
    vi.spyOn(apiMod.api, "getPredict").mockResolvedValue({
      status: "unavailable",
      reason: "offseason",
    } as never);
  }

  it("renders the header, the full funnel, and all five sections", async () => {
    stubHonestDefault();
    render(<HowItWorksPage />);
    // header
    expect(screen.getByText(/How CourtVision works/i)).toBeTruthy();
    // WhatAmILookingAt
    expect(screen.getByLabelText(/what am I looking at/i)).toBeTruthy();
    // FunnelDetail (all six stage labels)
    for (const l of ["DATA", "SIGNALS", "MODELS", "ENGINES", "ONE PREDICTION", "INTELLIGENCE"]) {
      expect(screen.getByText(l)).toBeTruthy();
    }
    // ValidationDiscipline
    expect(screen.getByLabelText(/validation discipline/i)).toBeTruthy();
    // HonestFindings
    expect(screen.getByLabelText(/honest findings/i)).toBeTruthy();
    // SelfImproveExplainer
    expect(screen.getByLabelText(/self-improve ratchet/i)).toBeTruthy();
    // the live example settles into its honest empty state
    await waitFor(() =>
      expect(screen.getByText(/No live soccer snapshot right now/i)).toBeTruthy()
    );
  });

  it("carries the page-level calibration-not-edge disclaimer and no-$ framing", async () => {
    stubHonestDefault();
    render(<HowItWorksPage />);
    expect(screen.getAllByText(/Calibration, not a market edge/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/No dollar edge is claimed/i).length).toBeGreaterThan(0);
  });

  it("both nav Links carry focus-visible ring classes consistent with GameCard token", () => {
    stubHonestDefault();
    const { container } = render(<HowItWorksPage />);
    // The page renders two navigation links at the bottom. Both must carry
    // focus-visible:ring-2 so keyboard users get a visible focus indicator
    // consistent with the GameCard focus-visible ring token pattern.
    const links = container.querySelectorAll("a");
    const navLinks = Array.from(links).filter(
      (a) =>
        a.getAttribute("href") === "/games" ||
        a.getAttribute("href") === "/system",
    );
    expect(navLinks).toHaveLength(2);
    for (const link of navLinks) {
      const cls = link.getAttribute("class") ?? "";
      expect(cls).toContain("focus-visible:outline-none");
      expect(cls).toContain("focus-visible:ring-2");
      expect(cls).toContain("focus-visible:ring-ring");
    }
  });

  it("renders NO dollar money-figure anywhere on the page", async () => {
    stubHonestDefault();
    const { container } = render(<HowItWorksPage />);
    await waitFor(() =>
      expect(screen.getByText(/No live soccer snapshot right now/i)).toBeTruthy()
    );
    const txt = container.textContent ?? "";
    // ban a dollar VALUE (the page may write the honesty phrase "no $ field");
    expect(/\$\s*\d/.test(txt)).toBe(false);
    expect(/\d\s*(dollars?|usd)\b/i.test(txt)).toBe(false);
    expect(/\bROI\b/.test(txt)).toBe(false);
  });
});
