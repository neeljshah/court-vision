import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";

// Home (/) deep-render tests -- the cohesive, honest front door.
//
// Asserts the front page renders, in order, the four honest pillars:
//   * Hero (PRODUCT_NAME + the "no dollar edge is claimed" framing)
//   * the HOW IT WORKS funnel strip (all six FUNNEL_STAGES labels)
//   * the live status row (delegated to HomeStatusRow -- mocked here)
//   * the entry cards (Games / How it works / System)
//   * the honest headline findings + the "Calibration, not a market edge" line
// and that NO dollar figure appears anywhere in the rendered Home output.
//
// HomeStatusRow does its own fetching; we stub its two source functions so the
// page renders deterministically with the HONEST default cells.

// next/link -> plain anchor so the server component renders under jsdom.
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

import Home from "../page";
import { FUNNEL_STAGES, HONEST_FINDINGS, PRODUCT_NAME } from "@/lib/api";
import * as apiMod from "@/lib/api";

describe("Home (/) -- the cohesive honest front page", () => {
  beforeEach(() => {
    // HomeStatusRow's two real-endpoint calls -> honest default values.
    vi.spyOn(apiMod, "getProductStatus").mockResolvedValue({
      allHonest: true,
      allHonestReason: "no face serves a $ field",
      selfImprove: "READY_INERT",
      selfImproveLabel: "self-improve: READY (not enabled)",
      realMoney: "DENY",
      liveSports: ["soccer"],
      edgeClaimed: false,
    } as never);
    vi.spyOn(apiMod, "getParityHeadline").mockResolvedValue({
      green: true,
      nSports: 4,
      reason: "fully green",
    } as never);
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders the hero with the product name and the no-dollar-edge framing", () => {
    render(<Home />);
    expect(screen.getAllByText(new RegExp(PRODUCT_NAME)).length).toBeGreaterThan(0);
    // the no-dollar-edge line appears in both the hero and the findings disclaimer
    expect(screen.getAllByText(/no dollar edge is claimed/i).length).toBeGreaterThan(0);
    // hero has the two primary CTAs
    expect(screen.getByText(/view games/i)).toBeTruthy();
  });

  it("renders the funnel strip with all six stage labels", () => {
    render(<Home />);
    const funnel = screen.getByLabelText(/how it works funnel/i);
    for (const stage of FUNNEL_STAGES) {
      expect(within(funnel).getByText(stage.label)).toBeTruthy();
    }
    // numeric step prefixes 01..06 present
    expect(within(funnel).getByText("01")).toBeTruthy();
    expect(within(funnel).getByText("06")).toBeTruthy();
  });

  it("renders the three entry cards linking Games / How it works / System", () => {
    render(<Home />);
    const games = screen.getAllByRole("link", { name: /games/i });
    expect(games.length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /how it works/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /system/i }).length).toBeGreaterThan(0);
    // the System card explicitly frames self-improve as READY, not enabled
    expect(screen.getByText(/READY, not enabled/i)).toBeTruthy();
  });

  it("renders every honest headline finding plus the calibration-not-edge line", () => {
    render(<Home />);
    const findings = screen.getByLabelText(/honest findings/i);
    for (const f of HONEST_FINDINGS) {
      expect(within(findings).getByText(f.title)).toBeTruthy();
    }
    expect(screen.getAllByText(/Calibration, not a market edge/i).length).toBeGreaterThan(0);
  });

  it("frames the system as efficient (no edge) and paper-only via the disclaimer", () => {
    render(<Home />);
    expect(screen.getAllByText(/Markets are efficient/i).length).toBeGreaterThan(0);
  });

  it("renders NO dollar money-figure anywhere in the Home output", () => {
    const { container } = render(<Home />);
    const txt = container.textContent ?? "";
    // The product legitimately writes the honesty phrase "no $ edge" / "$ field",
    // so we ban a dollar VALUE (a $ followed by a number), plus ROI/P&L framing.
    expect(/\$\s*\d/.test(txt)).toBe(false);
    expect(/\d\s*(dollars?|usd)\b/i.test(txt)).toBe(false);
    expect(/\bROI\b/.test(txt)).toBe(false);
    expect(/\bP&L\b|\bPnL\b/i.test(txt)).toBe(false);
  });

  // -------------------------------------------------------------------------
  // Focus-visible ring: every interactive <Link> on the home page must carry
  // the established keyboard-focus ring pattern (matching GameCard.tsx).
  // -------------------------------------------------------------------------

  it("Hero 'View Games' link has focus-visible ring classes", () => {
    render(<Home />);
    // getAllByRole('link') returns all anchors; find by text.
    const link = screen.getByRole("link", { name: /view games/i });
    expect(link.className).toMatch(/focus-visible:outline-none/);
    expect(link.className).toMatch(/focus-visible:ring-2/);
    expect(link.className).toMatch(/focus-visible:ring-ring/);
    expect(link.className).toMatch(/focus-visible:ring-offset-1/);
  });

  it("Hero 'How it works' link has focus-visible ring classes", () => {
    render(<Home />);
    // The hero has a 'How it works' link (separate from the EntryCards one).
    const links = screen.getAllByRole("link", { name: /how it works/i });
    // At least one of them should be in the Hero (no aria-label distinguishes
    // them; we just assert that every one carries the ring).
    for (const link of links) {
      expect(link.className).toMatch(/focus-visible:outline-none/);
      expect(link.className).toMatch(/focus-visible:ring-2/);
      expect(link.className).toMatch(/focus-visible:ring-ring/);
    }
  });

  it("all three EntryCard links have focus-visible ring classes", () => {
    render(<Home />);
    // EntryCards renders /games, /how-it-works, /system -- match by href.
    const allLinks = screen.getAllByRole("link") as HTMLAnchorElement[];
    const entryHrefs = ["/games", "/how-it-works", "/system"];
    for (const href of entryHrefs) {
      const match = allLinks.find((l) => l.getAttribute("href") === href);
      expect(match, `entry card link for ${href} not found`).toBeTruthy();
      expect(match!.className).toMatch(/focus-visible:outline-none/);
      expect(match!.className).toMatch(/focus-visible:ring-2/);
      expect(match!.className).toMatch(/focus-visible:ring-ring/);
      expect(match!.className).toMatch(/focus-visible:ring-offset-1/);
    }
  });

  it("every <Link> on the page carries a focus-visible:ring-2 class", () => {
    render(<Home />);
    const allLinks = screen.getAllByRole("link");
    for (const link of allLinks) {
      expect(
        link.className,
        `link '${link.textContent?.trim()}' (href=${link.getAttribute("href")}) missing focus-visible:ring-2`,
      ).toMatch(/focus-visible:ring-2/);
    }
  });
});
