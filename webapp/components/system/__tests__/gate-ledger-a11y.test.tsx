import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import * as sysMod from "../systemApi";
import type { FunnelArtifacts } from "../systemApi";

// gate-ledger-a11y -- the sortable gate-verdict ledger header must be operable
// and announce its state to assistive tech. SHARED-component a11y, kept in a
// new lane-disjoint test file (does NOT touch existing system-deep.test.tsx).
//
// Asserts: sortable column headers are real <button>s with aria-labels, the
// owning <th> carries aria-sort reflecting the live sort direction, and the
// verdict is rendered as TEXT (not color alone). No $ token.

import { GateLedgerPanel } from "../GateLedgerPanel";

function artifacts(): FunnelArtifacts {
  return {
    status: "ok",
    ledger: {
      rows: [
        {
          id: "r1",
          sport: "soccer",
          layer: "corners_calib",
          verdict: "SHIP",
          deciding_stat: "held-out Brier delta",
          corpora: 2,
          vs_close: "UNPROVEN -- no in-play price",
          base: "",
          source: "funnel",
        },
        {
          id: "r2",
          sport: "nba",
          layer: "ingame_microstate",
          verdict: "REJECT",
          deciding_stat: "clustered-DM p ~= 0.4",
          corpora: 3,
          vs_close: "UNPROVEN",
          base: "champion-elo",
          source: "funnel",
        },
      ],
      counts: { SHIP: 1, REJECT: 1 },
    },
    backlog: null,
    honest_note: "A REJECT is a SUCCESS. vs_close UNPROVEN everywhere.",
    edge_claimed: false,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(sysMod.systemApi, "artifacts").mockResolvedValue(artifacts());
});

describe("GateLedgerPanel sortable-header a11y", () => {
  it("sortable headers are buttons with aria-labels; <th> carries aria-sort", async () => {
    const { container } = render(<GateLedgerPanel />);
    // Wait for the async artifacts fetch to populate the table.
    await screen.findByText("corners_calib");

    const sortBtn = screen.getByRole("button", { name: /sort by sport/i });
    expect(sortBtn.tagName).toBe("BUTTON");

    // Default sort is "verdict" (active). Its <th> should be ascending; the
    // other sortable headers should be "none".
    const headers = container.querySelectorAll("th[aria-sort]");
    expect(headers.length).toBeGreaterThanOrEqual(4);
    const sortStates = Array.from(headers).map((h) => h.getAttribute("aria-sort"));
    expect(sortStates).toContain("ascending");
    expect(sortStates).toContain("none");
  });

  it("toggling a sort header flips its aria-sort to descending", async () => {
    const { container } = render(<GateLedgerPanel />);
    await screen.findByText("corners_calib");

    const sportBtn = screen.getByRole("button", { name: /sort by sport/i });
    // First click -> ascending on the sport column.
    fireEvent.click(sportBtn);
    await waitFor(() => {
      const sportTh = container
        .querySelector("th[aria-sort='ascending']");
      expect(sportTh?.textContent || "").toMatch(/sport/i);
    });
    // Second click -> descending.
    fireEvent.click(screen.getByRole("button", { name: /sort by sport/i }));
    await waitFor(() => {
      const sportTh = container.querySelector("th[aria-sort='descending']");
      expect(sportTh?.textContent || "").toMatch(/sport/i);
    });
  });

  it("renders verdict as text and prints no $ value", async () => {
    const { container } = render(<GateLedgerPanel />);
    await screen.findByText("corners_calib");
    // "SHIP"/"REJECT" appear both in the Legend and as the row verdict chip.
    expect(screen.getAllByText("SHIP").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("REJECT").length).toBeGreaterThanOrEqual(1);
    expect(container.textContent || "").not.toMatch(/\$\s?\d/);
  });
});
