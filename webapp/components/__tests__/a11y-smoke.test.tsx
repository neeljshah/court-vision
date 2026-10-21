import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within, fireEvent } from "@testing-library/react";

// a11y-smoke -- a focused accessibility baseline for the SHARED components a
// keyboard / screen-reader user touches on every page: the Nav, the InfoTip
// affordance, the gate-verdict chip, the sortable ledger header, the skip-link,
// and the first-run onboarding overlay.
//
// This is a SMOKE test (roles / aria / text-not-color-only / focusability), not
// an exhaustive audit. It lives in a dedicated, lane-disjoint __tests__ dir.
//
// Honesty rails still apply: no $ token, honest framing preserved.

// next/navigation is needed by Nav (usePathname). Stub it.
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

import { SiteHeader } from "../shell/SiteHeader";
import { InfoTip } from "../depth/InfoTip";
import { SignalVerdictBadge } from "../depth/SignalVerdictBadge";
import { OnboardingOverlay } from "../onboarding/OnboardingOverlay";

// ProductStatusBadges (rendered inside Nav at xl) fetches a real endpoint; stub
// it so the smoke test does not hit the network.
beforeEach(() => {
  localStorage.clear();
  global.fetch = vi.fn(() =>
    Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({}) }),
  ) as unknown as typeof fetch;
});

function noDollar(container: HTMLElement) {
  // No $<digit> money value should ever reach the DOM.
  expect(container.textContent || "").not.toMatch(/\$\s?\d/);
}

describe("a11y smoke -- SiteHeader", () => {
  it("exposes a banner + named navigation landmark with focusable links", () => {
    const { container } = render(<SiteHeader />);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    const main = screen.getByRole("navigation", { name: "Main" });
    const links = within(main).getAllByRole("link");
    expect(links.length).toBeGreaterThanOrEqual(5);
    links.forEach((l) => expect(l).toHaveAttribute("href"));
    noDollar(container);
  });

  it("marks the active route with aria-current=page (not color alone)", () => {
    render(<SiteHeader />);
    const current = screen
      .getAllByRole("link")
      .filter((l) => l.getAttribute("aria-current") === "page");
    expect(current.length).toBeGreaterThanOrEqual(1);
  });

  it("theme + mobile toggles have aria-labels (icon-only buttons)", () => {
    render(<SiteHeader />);
    // The toggle is a pressed-state button ("Dark theme", aria-pressed), the menu a disclosure.
    expect(screen.getByRole("button", { name: "Dark theme" })).toHaveAttribute("aria-pressed");
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
  });
});

describe("a11y smoke -- InfoTip", () => {
  it("is a real button with an accessible name (keyboard-focusable)", () => {
    render(<InfoTip text="Closing Line Value." ariaLabel="what is CLV?" />);
    const btn = screen.getByRole("button", { name: /what is clv\?/i });
    expect(btn).toBeInTheDocument();
    expect(btn.tagName).toBe("BUTTON");
  });
});

describe("a11y smoke -- SignalVerdictBadge", () => {
  it("shows the verdict as TEXT, not color alone (SHIP)", () => {
    const { container } = render(<SignalVerdictBadge verdict="SHIP" />);
    expect(screen.getByText("CALIBRATION SURVIVOR -- NOT SHIPPED")).toBeInTheDocument();
    // SHIP always carries the calibration-only honest framing as visible text.
    expect(
      screen.getByText(/calibration-only, vs_close UNPROVEN/i),
    ).toBeInTheDocument();
    noDollar(container);
  });

  it("shows REJECT verdict word as text", () => {
    render(<SignalVerdictBadge verdict="REJECT" />);
    expect(screen.getByText("REJECT")).toBeInTheDocument();
  });
});

describe("a11y smoke -- OnboardingOverlay", () => {
  it("opens from the Help button with a dialog + named sections + honest rails", async () => {
    const { container } = render(<OnboardingOverlay />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /open the how-to-read-this guide/i }),
    );
    // Radix Dialog opens => role=dialog with an accessible title.
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/what is this & how to read it/i),
    ).toBeInTheDocument();
    // The four honest rails are present as visible text.
    expect(within(dialog).getByText(/Units, not dollars/i)).toBeInTheDocument();
    expect(
      within(dialog).getByText(/Calibration, not a market edge/i),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(/READY but INERT/i),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(/Real money: DENY/i)).toBeInTheDocument();
    // Page map links every product area (the six shell destinations, in order).
    const mapLinks = within(dialog).getAllByRole("link").map((l) => l.textContent ?? "");
    ["Home", "Games", "Desk", "Paper record", "Desk health", "How it works"].forEach((label, i) => {
      expect(mapLinks[i]).toContain(label);
    });
    noDollar(container);
  });

  it("does NOT auto-open once the seen flag is set, but the Help button is present", async () => {
    localStorage.setItem("cv-onboarded", "1");
    render(<OnboardingOverlay />);
    // Persistent Help affordance is always rendered + labelled.
    const help = await screen.findByRole("button", {
      name: /open the how-to-read-this guide/i,
    });
    expect(help).toBeInTheDocument();
    // No dialog auto-opens.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
