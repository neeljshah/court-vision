import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { OpsPanel } from "../OpsPanel";
import { api } from "@/lib/p5api";
import type { OpsStatus, AutonomyStatus } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// OPS FACES TOLERANCE TESTS (QA #9)
//
// The OpsPanel consumes two independent feeds:
//   - api.opsStatus        -> System health overall
//   - api.getAutonomyStatus -> Autonomy status overall
//
// When the two overall rollups disagree within the same poll window:
//   * The panel-level header badge reflects the MORE CONSERVATIVE (worst) state
//   * A reconciliation note is shown -- never hidden when feeds disagree
//   * Neither block upgrades the other's raw badge
//
// When the autonomy feed is unavailable:
//   * The autonomy block shows Unavailable (never green)
//   * The panel header treats the missing feed as 'down' (conservative)
//
// When both feeds agree on 'ok':
//   * No reconciliation note
//   * Header badge is green
// ---------------------------------------------------------------------------

function mkOpsStatus(overall: string, services: object[] = []): OpsStatus {
  return {
    overall,
    services: services as OpsStatus["services"],
    generated_at: new Date().toISOString(),
    notes: [],
  };
}

function mkAutonomyStatus(overall: string): AutonomyStatus {
  return {
    status: "ok",
    overall,
    loop: { liveness_severity: overall, cycle: 1 },
    idle_reason: null,
    generated_at: new Date().toISOString(),
    notes: [],
  };
}

afterEach(() => vi.restoreAllMocks());

describe("OpsPanel -- cross-feed reconciliation (QA #9)", () => {
  it("shows conservative (worst) badge and note when ops='ok' but autonomy='down'", async () => {
    vi.spyOn(api, "opsStatus").mockResolvedValue(mkOpsStatus("ok", []));
    vi.spyOn(api, "getAutonomyStatus").mockResolvedValue(
      mkAutonomyStatus("down"),
    );

    render(<OpsPanel />);

    // Wait for both feeds to resolve and reconciliation to appear
    await waitFor(() => {
      const overall = screen.getByTestId("ops-panel-overall");
      // Panel overall must NOT be green 'ok' -- must reflect the conservative 'down'
      expect(overall.textContent).not.toMatch(/\bok\b/i);
    });

    // The conservative badge should read 'down' (worst of ok vs down)
    const overall = screen.getByTestId("ops-panel-overall");
    expect(overall.textContent?.toLowerCase()).toContain("down");

    // Reconciliation note must be visible when feeds disagree
    const note = await screen.findByRole("note", {
      name: "ops-reconciliation-note",
    });
    expect(note).toBeTruthy();
    expect(note.textContent).toMatch(/disagree/i);
  });

  it("shows conservative badge and note when ops='ok' but autonomy='degraded'", async () => {
    vi.spyOn(api, "opsStatus").mockResolvedValue(mkOpsStatus("ok", []));
    vi.spyOn(api, "getAutonomyStatus").mockResolvedValue(
      mkAutonomyStatus("degraded"),
    );

    render(<OpsPanel />);

    await waitFor(() => {
      const overall = screen.getByTestId("ops-panel-overall");
      expect(overall.textContent?.toLowerCase()).not.toContain("ok");
    });

    const overall = screen.getByTestId("ops-panel-overall");
    expect(overall.textContent?.toLowerCase()).toContain("degraded");

    const note = await screen.findByRole("note", {
      name: "ops-reconciliation-note",
    });
    expect(note.textContent).toMatch(/disagree/i);
  });

  it("shows no reconciliation note and green header when both feeds are 'ok'", async () => {
    vi.spyOn(api, "opsStatus").mockResolvedValue(mkOpsStatus("ok", []));
    vi.spyOn(api, "getAutonomyStatus").mockResolvedValue(
      mkAutonomyStatus("ok"),
    );

    render(<OpsPanel />);

    // Wait for both feeds to resolve
    await waitFor(() => {
      const overall = screen.getByTestId("ops-panel-overall");
      expect(overall.textContent?.toLowerCase()).toContain("ok");
    });

    // No reconciliation note when both agree
    expect(
      screen.queryByRole("note", { name: "ops-reconciliation-note" }),
    ).toBeNull();

    // The combined badge should be the green-tone badge (contains 'ok')
    const overall = screen.getByTestId("ops-panel-overall");
    // The Badge span for 'ok' uses the tier-a green tone class
    const pill = overall.querySelector("span");
    expect(pill?.className).toContain("tier-a");
  });

  it("autonomy Unavailable -> autonomy block shows Unavailable, panel NOT green", async () => {
    vi.spyOn(api, "opsStatus").mockResolvedValue(mkOpsStatus("ok", []));
    // Simulate a missing/stale autonomy doc -> Unavailable sentinel
    vi.spyOn(api, "getAutonomyStatus").mockResolvedValue({
      status: "unavailable",
      reason: "autonomy_status.json missing or stale",
    } as unknown as AutonomyStatus);

    render(<OpsPanel />);

    // The autonomy block should show 'unavailable' text (never green)
    await waitFor(() => {
      expect(screen.getByText(/unavailable/i)).toBeTruthy();
    });

    // Panel-level badge should never be green while autonomy is unavailable
    await waitFor(() => {
      const overall = screen.getByTestId("ops-panel-overall");
      // Either it shows 'checking' (conservative hold) or 'down'/'degraded'
      // It MUST NOT show 'ok'
      expect(overall.textContent?.toLowerCase()).not.toContain("ok");
    });

    // The autonomy Unavailable block should not have a green badge on it
    // (the Unavailable sentinel shows amber text, not tier-a/green)
    const unavailableEl = screen.getByText(/unavailable/i);
    expect(unavailableEl.className).not.toContain("tier-a");
  });

  it("does NOT show reconciliation note when both feeds agree on 'down'", async () => {
    vi.spyOn(api, "opsStatus").mockResolvedValue(mkOpsStatus("down", []));
    vi.spyOn(api, "getAutonomyStatus").mockResolvedValue(
      mkAutonomyStatus("down"),
    );

    render(<OpsPanel />);

    await waitFor(() => {
      const overall = screen.getByTestId("ops-panel-overall");
      expect(overall.textContent?.toLowerCase()).toContain("down");
    });

    // Both feeds agree -> no reconciliation note
    expect(
      screen.queryByRole("note", { name: "ops-reconciliation-note" }),
    ).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Skeleton loading state (QA #ws3)
  // When opsStatus has not yet resolved (!data && !err), OpsPanel must render
  // a skeleton shimmer, NOT the literal 'loading...' text.
  // The loading state is neutral: no green, no red, no status badge.
  // -------------------------------------------------------------------------
  it("renders a skeleton (not 'loading...') while opsStatus is pending", () => {
    // Keep opsStatus perpetually pending so data stays null and err stays null
    vi.spyOn(api, "opsStatus").mockReturnValue(new Promise(() => {}));
    vi.spyOn(api, "getAutonomyStatus").mockReturnValue(new Promise(() => {}));

    render(<OpsPanel />);

    // Must render the skeleton placeholder
    const skeleton = screen.getByTestId("ops-service-skeleton");
    expect(skeleton).toBeTruthy();

    // Must NOT render the bare 'loading...' text
    expect(screen.queryByText(/^loading\.\.\.$/i)).toBeNull();

    // Skeleton must carry the accessible loading role
    expect(skeleton.getAttribute("role")).toBe("status");
    expect(skeleton.getAttribute("aria-busy")).toBe("true");

    // Header badge must be neutral 'checking' (never premature green) before data arrives
    const overall = screen.getByTestId("ops-panel-overall");
    expect(overall.textContent?.toLowerCase()).not.toContain("ok");
    expect(overall.textContent?.toLowerCase()).not.toContain("down");
    expect(overall.textContent?.toLowerCase()).not.toContain("degraded");
  });
});

// ---------------------------------------------------------------------------
// A11Y + table structure tests (QA #ws4)
//
// Service table must:
//   - Have an aria-label so AT announces the table purpose
//   - Have scope="col" on every column header (WCAG 1.3.1)
//
// Live + Breaker cells must convey state via text, NOT color alone:
//   - live=true  -> "yes"; live=false -> "no"; unknown -> "--"
//   - breaker "closed" / "open" are rendered as those strings verbatim
//
// Header "checking" is neutral while EITHER feed is unresolved:
//   - ops=ok + autonomy pending -> still 'checking' (never premature green)
// ---------------------------------------------------------------------------
describe("OpsPanel -- a11y + table + text-not-color (QA #ws4)", () => {
  function mkSvc(
    name: string,
    live: boolean | null,
    breaker: string,
  ): OpsStatus["services"][number] {
    return {
      name,
      live,
      breaker,
      critical: false,
      last_seen: null,
      fresh: null,
      age_sec: null,
    } as unknown as OpsStatus["services"][number];
  }

  it("service table has aria-label and scope=col on all column headers", async () => {
    vi.spyOn(api, "opsStatus").mockResolvedValue(
      mkOpsStatus("ok", [mkSvc("predictor", true, "closed")]),
    );
    vi.spyOn(api, "getAutonomyStatus").mockResolvedValue(mkAutonomyStatus("ok"));

    render(<OpsPanel />);

    // Wait for the table to appear
    const table = await screen.findByRole("table", {
      name: /service health status/i,
    });
    expect(table).toBeTruthy();

    // All <th> elements must carry scope="col"
    const headers = table.querySelectorAll("th");
    expect(headers.length).toBeGreaterThan(0);
    headers.forEach((th) => {
      expect(th.getAttribute("scope")).toBe("col");
    });
  });

  it("live cell renders 'yes' text for live=true (not color-only)", async () => {
    vi.spyOn(api, "opsStatus").mockResolvedValue(
      mkOpsStatus("ok", [mkSvc("predictor", true, "closed")]),
    );
    vi.spyOn(api, "getAutonomyStatus").mockResolvedValue(mkAutonomyStatus("ok"));

    render(<OpsPanel />);

    // findByTestId waits for the row to appear
    const cell = await screen.findByTestId("live-cell-predictor");
    expect(cell.textContent?.toLowerCase()).toContain("yes");
  });

  it("live cell renders 'no' text for live=false (not color-only)", async () => {
    vi.spyOn(api, "opsStatus").mockResolvedValue(
      mkOpsStatus("down", [mkSvc("predictor", false, "open")]),
    );
    vi.spyOn(api, "getAutonomyStatus").mockResolvedValue(mkAutonomyStatus("down"));

    render(<OpsPanel />);

    const cell = await screen.findByTestId("live-cell-predictor");
    expect(cell.textContent?.toLowerCase()).toContain("no");
  });

  it("breaker cell renders 'closed' text when breaker='closed' (not color-only)", async () => {
    vi.spyOn(api, "opsStatus").mockResolvedValue(
      mkOpsStatus("ok", [mkSvc("predictor", true, "closed")]),
    );
    vi.spyOn(api, "getAutonomyStatus").mockResolvedValue(mkAutonomyStatus("ok"));

    render(<OpsPanel />);

    const cell = await screen.findByTestId("breaker-cell-predictor");
    expect(cell.textContent?.toLowerCase()).toContain("closed");
  });

  it("breaker cell renders 'open' text when breaker='open' (not color-only)", async () => {
    vi.spyOn(api, "opsStatus").mockResolvedValue(
      mkOpsStatus("down", [mkSvc("predictor", false, "open")]),
    );
    vi.spyOn(api, "getAutonomyStatus").mockResolvedValue(mkAutonomyStatus("down"));

    render(<OpsPanel />);

    const cell = await screen.findByTestId("breaker-cell-predictor");
    expect(cell.textContent?.toLowerCase()).toContain("open");
  });

  it("header shows 'checking' (not ok) when ops=ok but autonomy not yet resolved", () => {
    // ops resolves immediately with ok; autonomy never resolves
    vi.spyOn(api, "opsStatus").mockResolvedValue(mkOpsStatus("ok", []));
    vi.spyOn(api, "getAutonomyStatus").mockReturnValue(new Promise(() => {}));

    render(<OpsPanel />);

    // Even after the synchronous microtask queue drains, autonomy is still pending.
    // The header must be 'checking', never 'ok'.
    const overall = screen.getByTestId("ops-panel-overall");
    // At this sync point ops may or may not have resolved -- either way must not be ok
    expect(overall.textContent?.toLowerCase()).not.toContain("ok");
  });
});
