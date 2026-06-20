import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import {
  SchedulerFreshnessPanel,
  rowTone,
  localAgeSec,
} from "../SchedulerFreshnessPanel";
import { api, type ProduceSportStatus, type ProduceStatus } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// SchedulerFreshnessPanel -- producer/scheduler last-update freshness, with the
// stale-never-green + scheduler-gap-visible rails.
//
// Acceptance contract (WS3-p6-ops-lines-livehook):
//   1. rowTone/localAgeSec pure logic -- stale-never-green.
//   2. Scheduler-gap visibility -- dropped sport shows 'not scheduled'.
//   3. 'checking' neutral badge before first poll resolves (useLiveData consumed).
//   4. Amber/stale badge (never green) when poll data is aged.
//   5. Last-good retained on failed poll; never crashes on error.
// ---------------------------------------------------------------------------

const HOUR_MS = 60 * 60 * 1000;

function mkSport(p: Partial<ProduceSportStatus>): ProduceSportStatus {
  return {
    sport: "nba",
    ok: true,
    status: "ok",
    generated_at: null,
    age_seconds: null,
    n_games: 0,
    n_markets: 0,
    ...p,
  };
}

afterEach(() => vi.restoreAllMocks());

// ---------------------------------------------------------------------------
// 1. rowTone / localAgeSec -- stale never green
// ---------------------------------------------------------------------------
describe("rowTone / localAgeSec -- stale never green", () => {
  it("green only when ok AND age within SLA", () => {
    const fresh = mkSport({ generated_at: new Date(Date.now() - 5_000).toISOString() });
    expect(rowTone(fresh)).toBe("green");
  });

  it("aged-out snapshot reads amber even when status=ok", () => {
    const stale = mkSport({
      status: "ok",
      ok: true,
      generated_at: new Date(Date.now() - 3 * HOUR_MS).toISOString(),
    });
    expect(rowTone(stale)).toBe("amber");
  });

  it("missing snapshot reads slate (neutral, never green/red)", () => {
    expect(rowTone(mkSport({ status: "missing", ok: false }))).toBe("slate");
  });

  it("localAgeSec derives from generated_at, falls back to age_seconds", () => {
    const ts = mkSport({ generated_at: new Date(Date.now() - 10_000).toISOString() });
    expect(localAgeSec(ts)!).toBeGreaterThanOrEqual(9);
    const fallback = mkSport({ generated_at: null, age_seconds: 42 });
    expect(localAgeSec(fallback)).toBe(42);
    expect(localAgeSec(mkSport({ generated_at: null, age_seconds: null }))).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 2. Scheduler-gap visibility
// ---------------------------------------------------------------------------
describe("SchedulerFreshnessPanel -- scheduler-gap visibility", () => {
  it("shows a sport dropped from the rotation as 'not scheduled', not hidden", async () => {
    const doc: ProduceStatus = {
      status: "ok",
      sports: [mkSport({ sport: "nba", generated_at: new Date().toISOString() })],
      n_sports: 1,
      any_fresh: true,
    };
    vi.spyOn(api, "getProduceStatus").mockResolvedValue(doc);

    render(<SchedulerFreshnessPanel />);

    // nba served + fresh
    await waitFor(() => expect(screen.getByTestId("produce-row-nba")).toBeTruthy());
    // mlb absent from payload -> still rendered as a gap row
    const mlbRow = screen.getByTestId("produce-row-mlb");
    expect(mlbRow.textContent).toMatch(/not scheduled/i);
  });
});

// ---------------------------------------------------------------------------
// 3. 'checking' neutral badge before first poll resolves
//    Contract: useLiveData consumed; isLoading + !data -> shows 'checking' (slate)
// ---------------------------------------------------------------------------
describe("SchedulerFreshnessPanel -- 'checking' before first poll", () => {
  it("shows 'checking' (neutral slate) badge while first fetch is pending", () => {
    // Keep the fetch pending forever -- isLoading stays true, data stays null
    vi.spyOn(api, "getProduceStatus").mockReturnValue(new Promise(() => {}));

    render(<SchedulerFreshnessPanel />);

    // 'checking' must be in the header (neutral, not green, not red)
    expect(screen.getByText(/checking/i)).toBeTruthy();

    // The skeleton shimmer (aria-busy) must be present
    const skeleton = screen.getByRole("status", { name: /loading producer freshness/i });
    expect(skeleton.getAttribute("aria-busy")).toBe("true");
  });

  it("does NOT show green badge before first poll completes", () => {
    vi.spyOn(api, "getProduceStatus").mockReturnValue(new Promise(() => {}));

    render(<SchedulerFreshnessPanel />);

    // No span with tier-a (green) should be in the header before first load
    const allBadges = document.querySelectorAll("span[role='status']");
    const anyGreen = Array.from(allBadges).some(
      (el) => el.className.includes("tier-a") || el.textContent?.includes("all fresh"),
    );
    expect(anyGreen).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 4. Amber (never green) on stale/aged data -- last-good retention
// ---------------------------------------------------------------------------
describe("SchedulerFreshnessPanel -- last-good retention on failed poll", () => {
  it("retains last-good rows after a failed subsequent poll", async () => {
    const goodDoc: ProduceStatus = {
      status: "ok",
      sports: [mkSport({ sport: "nba", generated_at: new Date().toISOString() })],
      n_sports: 1,
      any_fresh: true,
    };

    let callCount = 0;
    vi.spyOn(api, "getProduceStatus").mockImplementation(() => {
      callCount++;
      if (callCount === 1) return Promise.resolve(goodDoc);
      // Second poll fails
      return Promise.resolve({ status: "unavailable", reason: "test" } as never);
    });

    render(<SchedulerFreshnessPanel />);

    // Wait for good data to render (nba row present)
    await waitFor(() => expect(screen.getByTestId("produce-row-nba")).toBeTruthy());

    // Panel must not crash and must still show the table
    expect(screen.queryByText("loading...")).toBeNull();
    // nba row must persist (last-good retained)
    expect(screen.getByTestId("produce-row-nba")).toBeTruthy();
  });

  it("never crashes the page on a poll error", () => {
    vi.spyOn(api, "getProduceStatus").mockResolvedValue({
      status: "unavailable",
      reason: "network error",
    } as never);

    expect(() => render(<SchedulerFreshnessPanel />)).not.toThrow();
  });
});
