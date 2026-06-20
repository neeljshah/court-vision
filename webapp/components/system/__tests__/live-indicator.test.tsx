import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { LiveIndicator } from "../LiveIndicator";

// ---------------------------------------------------------------------------
// LiveIndicator honesty-rail tests:
//   * GREEN ("LIVE - RUNNING INDEPENDENTLY") ONLY when the route returns
//     live:true (fresh + all_ready + no proc degraded).
//   * STALE / missing feed (live:false / 503 unavailable) NEVER renders green --
//     it shows IDLE/DEGRADED with the explicit reason, no fabricated uptime.
//   * A degraded proc (live:false, any_degraded:true) renders DEGRADED red.
//   * The static honest badges are always present (READY-but-INERT / DENY /
//     INSUFFICIENT_DATA) and NO $ token is rendered or present in source.
// ---------------------------------------------------------------------------

const realFetch = global.fetch;
afterEach(() => {
  global.fetch = realFetch;
  vi.restoreAllMocks();
});

const jsonRes = (body: unknown, status = 200, ok = true) => ({
  ok,
  status,
  headers: new Headers({ "content-type": "application/json" }),
  json: async () => body,
});

function mockFetch(body: unknown, status = 200, ok = true) {
  global.fetch = vi
    .fn()
    .mockResolvedValue(jsonRes(body, status, ok)) as unknown as typeof fetch;
}

const liveDoc = {
  status: "ok",
  live: true,
  overall: "ok",
  all_ready: true,
  any_degraded: false,
  n_procs: 2,
  restarts_total: 0,
  uptime_sec: 3600,
  age_sec: 5,
  procs: [
    { name: "m1_producer", state: "READY", ready: true, restarts: 0, degraded: false, heartbeat_age_sec: 4, heartbeat_fresh_sec: 300, kind: "heartbeat-file-fresh" },
    { name: "m4_selfimprove", state: "READY", ready: true, restarts: 1, degraded: false, heartbeat_age_sec: 20, heartbeat_fresh_sec: 300, kind: "heartbeat-file-fresh" },
  ],
  edge_claimed: false,
};

describe("LiveIndicator -- stale-never-green honesty rail", () => {
  it("renders GREEN LIVE only when live:true (fresh + all_ready + no degraded)", async () => {
    mockFetch(liveDoc);
    render(<LiveIndicator />);
    await waitFor(() =>
      expect(screen.getByText(/RUNNING INDEPENDENTLY/i)).toBeTruthy(),
    );
    expect(screen.getByText(/m1_producer/)).toBeTruthy();
  });

  it("NEVER green on a STALE / missing feed (503 unavailable)", async () => {
    mockFetch(
      { status: "unavailable", live: false, overall: "down", reason: "supervisor_status.json stale (68793s > 120s SLA)" },
      503,
      false,
    );
    render(<LiveIndicator />);
    // fetchHonest degrades a 503 to the Unavailable sentinel; banner must NOT be green.
    await waitFor(() =>
      expect(screen.getByText(/IDLE \/ DEGRADED/i)).toBeTruthy(),
    );
    expect(screen.queryByText(/RUNNING INDEPENDENTLY/i)).toBeNull();
  });

  it("NEGATIVE CONTROL: green-on-MISSING status file must NOT be green", async () => {
    // The route returns the SAME unavailable sentinel for an ABSENT
    // supervisor_status.json (distinct reason). A missing feed proves nothing is
    // running -> the banner must degrade to IDLE/DEGRADED and surface the missing
    // reason, never the green "RUNNING INDEPENDENTLY" badge or a fabricated uptime.
    mockFetch(
      {
        status: "unavailable",
        live: false,
        overall: "down",
        reason: "supervisor_status.json missing or unreadable",
        all_ready: false,
        procs: [],
        restarts_total: 0,
        uptime_sec: null,
        age_sec: null,
        edge_claimed: false,
      },
      503,
      false,
    );
    render(<LiveIndicator />);
    await waitFor(() =>
      expect(screen.getByText(/IDLE \/ DEGRADED/i)).toBeTruthy(),
    );
    // The green badge is impossible on a missing feed.
    expect(screen.queryByText(/RUNNING INDEPENDENTLY/i)).toBeNull();
    // The honest Unavailable sentinel is shown (no fabricated uptime/services).
    expect(screen.getByText(/unavailable/i)).toBeTruthy();
  });

  it("renders DEGRADED red when a proc is degraded (live:false)", async () => {
    mockFetch({
      ...liveDoc,
      live: false,
      overall: "down",
      any_degraded: true,
      reason: "m4_selfimprove heartbeat stale",
      procs: [
        { ...liveDoc.procs[0] },
        { ...liveDoc.procs[1], state: "RUNNING", degraded: true },
      ],
    });
    render(<LiveIndicator />);
    // DEGRADED shows in BOTH the banner and the degraded proc row -- both honest.
    await waitFor(() =>
      expect(screen.getAllByText(/^DEGRADED$/i).length).toBeGreaterThan(0),
    );
    expect(screen.queryByText(/RUNNING INDEPENDENTLY/i)).toBeNull();
  });

  it("always shows the static honest badges and NO edge claim", async () => {
    mockFetch(liveDoc);
    render(<LiveIndicator />);
    await waitFor(() =>
      expect(screen.getByText(/READY-but-INERT/i)).toBeTruthy(),
    );
    expect(screen.getByText(/real-money: DENY/i)).toBeTruthy();
    expect(screen.getByText(/INSUFFICIENT_DATA/i)).toBeTruthy();
  });

  it("contains NO $ token in the source files", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const comp = readFileSync(join(here, "..", "LiveIndicator.tsx"), "utf-8");
    const route = readFileSync(
      join(here, "..", "..", "..", "app", "api", "ops", "supervisor", "route.ts"),
      "utf-8",
    );
    // A rendered dollar AMOUNT is `$` adjacent to a digit (e.g. $0, $1.50). The
    // honest disclaimer copy ("no $", "$ field") is allowed; only currency is not.
    // Strip template-literal `${...}` interpolations first so they never match.
    const dollarAmount = /\$\s*\d/;
    const strip = (s: string) => s.replace(/\$\{[^}]*\}/g, "");
    expect(dollarAmount.test(strip(comp))).toBe(false);
    expect(dollarAmount.test(strip(route))).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// a11y -- roster table accessibility + headline keyboard discoverability
// ---------------------------------------------------------------------------

describe("LiveIndicator -- a11y polish (ws3-liveindicator-roster)", () => {
  it("roster table headers have scope=col", async () => {
    mockFetch(liveDoc);
    const { container } = render(<LiveIndicator />);
    await waitFor(() =>
      expect(screen.getByText(/m1_producer/)).toBeTruthy(),
    );
    const ths = container.querySelectorAll("th");
    expect(ths.length).toBe(4);
    ths.forEach((th) => {
      expect(th.getAttribute("scope")).toBe("col");
    });
  });

  it("roster table has an accessible name (aria-label)", async () => {
    mockFetch(liveDoc);
    const { container } = render(<LiveIndicator />);
    await waitFor(() =>
      expect(screen.getByText(/m1_producer/)).toBeTruthy(),
    );
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    // aria-label or caption satisfies accessible-name requirement.
    const hasLabel =
      table!.hasAttribute("aria-label") ||
      table!.hasAttribute("aria-labelledby") ||
      table!.querySelector("caption") !== null;
    expect(hasLabel).toBe(true);
  });

  it("headline span is keyboard-focusable (tabIndex=0) when live", async () => {
    mockFetch(liveDoc);
    const { container } = render(<LiveIndicator />);
    await waitFor(() =>
      expect(screen.getByText(/RUNNING INDEPENDENTLY/i)).toBeTruthy(),
    );
    // The headline text span must be reachable via keyboard (tabIndex >= 0).
    const headlineSpan = Array.from(container.querySelectorAll("span")).find(
      (el) => /RUNNING INDEPENDENTLY/i.test(el.textContent || ""),
    );
    expect(headlineSpan).not.toBeUndefined();
    const ti = headlineSpan!.getAttribute("tabindex");
    expect(Number(ti)).toBeGreaterThanOrEqual(0);
  });

  it("headline span is keyboard-focusable when IDLE/DEGRADED (stale feed)", async () => {
    mockFetch(
      { status: "unavailable", live: false, overall: "down", reason: "stale" },
      503,
      false,
    );
    const { container } = render(<LiveIndicator />);
    await waitFor(() =>
      expect(screen.getByText(/IDLE \/ DEGRADED/i)).toBeTruthy(),
    );
    const headlineSpan = Array.from(container.querySelectorAll("span")).find(
      (el) => /IDLE \/ DEGRADED/i.test(el.textContent || ""),
    );
    expect(headlineSpan).not.toBeUndefined();
    const ti = headlineSpan!.getAttribute("tabindex");
    expect(Number(ti)).toBeGreaterThanOrEqual(0);
  });

  it("status block has aria-live=polite and aria-atomic=true", async () => {
    mockFetch(liveDoc);
    const { container } = render(<LiveIndicator />);
    await waitFor(() =>
      expect(screen.getByText(/RUNNING INDEPENDENTLY/i)).toBeTruthy(),
    );
    const statusDiv = container.querySelector('[role="status"][aria-live]');
    expect(statusDiv).not.toBeNull();
    expect(statusDiv!.getAttribute("aria-live")).toBe("polite");
    expect(statusDiv!.getAttribute("aria-atomic")).toBe("true");
  });

  it("IDLE/DEGRADED for missing/stale feed uses amber (not red/failed) styling", async () => {
    mockFetch(
      {
        status: "unavailable",
        live: false,
        overall: "down",
        reason: "supervisor_status.json missing or unreadable",
        all_ready: false,
        procs: [],
        restarts_total: 0,
        uptime_sec: null,
        age_sec: null,
        edge_claimed: false,
      },
      503,
      false,
    );
    const { container } = render(<LiveIndicator />);
    await waitFor(() =>
      expect(screen.getByText(/IDLE \/ DEGRADED/i)).toBeTruthy(),
    );
    // The banner block must use amber classes, NOT red, for a plain stale/missing feed.
    const statusDiv = container.querySelector('[role="status"][aria-live]');
    expect(statusDiv).not.toBeNull();
    // amber class present
    expect(statusDiv!.className).toMatch(/amber/);
    // red class must NOT appear on the banner border/bg for a stale feed (only amber).
    // We check the specific red background token used for degraded procs.
    expect(statusDiv!.className).not.toMatch(/red-950/);
    expect(statusDiv!.className).not.toMatch(/red-900/);
    // The text shown is IDLE/DEGRADED (amber path), never "failed".
    expect(screen.queryByText(/failed/i)).toBeNull();
  });

  it("any_degraded:true yields red DEGRADED banner class", async () => {
    mockFetch({
      ...liveDoc,
      live: false,
      overall: "down",
      any_degraded: true,
      reason: "m4_selfimprove heartbeat stale",
      procs: [
        { ...liveDoc.procs[0] },
        { ...liveDoc.procs[1], state: "RUNNING", degraded: true },
      ],
    });
    const { container } = render(<LiveIndicator />);
    await waitFor(() =>
      expect(screen.getAllByText(/^DEGRADED$/i).length).toBeGreaterThan(0),
    );
    const statusDiv = container.querySelector('[role="status"][aria-live]');
    expect(statusDiv).not.toBeNull();
    // For a truly degraded proc, the banner should use red classes.
    expect(statusDiv!.className).toMatch(/red/);
  });
});

// ---------------------------------------------------------------------------
// WS6 -- useLiveData migration tests:
//   * LiveIndicator polls via useLiveData (real data refresh, not bare tick)
//   * Shows neutral "checking" before first data arrives
//   * Pauses polling when tab is hidden; resumes + refetches on visible
//   * Stale-never-green: isStale suppresses the green badge (shows "stale" amber)
//   * app/models/error.tsx exists as a Next.js error boundary
// ---------------------------------------------------------------------------

describe("LiveIndicator -- WS6 useLiveData migration", () => {
  // These tests use real timers (the initial fetch fires immediately on mount).
  // Fake timers are only enabled in tests that need to advance time.

  afterEach(() => {
    vi.useRealTimers();
    global.fetch = realFetch;
    vi.restoreAllMocks();
    Object.defineProperty(document, "hidden", { value: false, configurable: true, writable: true });
  });

  it("shows neutral 'checking' badge before first data arrives", () => {
    // Never resolves during this test -- verifies the pre-data state.
    global.fetch = vi.fn().mockReturnValue(new Promise(() => {})) as unknown as typeof fetch;
    const { container } = render(<LiveIndicator />);
    // The header right-slot badge reads 'checking' while isLoading=true and error=null.
    expect(container.textContent).toMatch(/checking/i);
    // The aria-label on the status div must also reflect the loading state.
    const statusDiv = container.querySelector('[role="status"][aria-live]');
    expect(statusDiv).not.toBeNull();
    expect(statusDiv!.getAttribute("aria-label")).toMatch(/checking/i);
  });

  it("shows 'checking...' in the headline span before first poll", () => {
    global.fetch = vi.fn().mockReturnValue(new Promise(() => {})) as unknown as typeof fetch;
    const { container } = render(<LiveIndicator />);
    // The headline span text (in the status block) reads "checking..."
    const headlineSpans = Array.from(container.querySelectorAll("span")).filter(
      (el) => /checking/i.test(el.textContent || ""),
    );
    expect(headlineSpans.length).toBeGreaterThan(0);
  });

  it("performs a real data fetch (useLiveData poll) and updates the UI", async () => {
    // Use a real resolved fetch -- useLiveData fires immediately on mount.
    let callCount = 0;
    global.fetch = vi.fn().mockImplementation(async () => {
      callCount += 1;
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => liveDoc,
      };
    }) as unknown as typeof fetch;

    render(<LiveIndicator />);

    // useLiveData fires the initial fetch immediately on mount.
    await waitFor(() => expect(callCount).toBeGreaterThanOrEqual(1));
    // After the fetch resolves the UI should show the live status.
    await waitFor(() =>
      expect(screen.getByText(/RUNNING INDEPENDENTLY/i)).toBeTruthy(),
    );
  });

  it("pauses polling while document.hidden (tab in background)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    let fetchCallCount = 0;
    global.fetch = vi.fn().mockImplementation(async () => {
      fetchCallCount += 1;
      return {
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => liveDoc,
      };
    }) as unknown as typeof fetch;

    render(<LiveIndicator />);

    // Drain the initial microtask queue so the first fetch fires and resolves.
    await act(async () => {
      await Promise.resolve();
    });
    await waitFor(() => expect(fetchCallCount).toBeGreaterThanOrEqual(1), { timeout: 3000 });
    const afterMount = fetchCallCount;

    // Hide the tab.
    Object.defineProperty(document, "hidden", { value: true, configurable: true, writable: true });
    document.dispatchEvent(new Event("visibilitychange"));

    // Advance past two polling intervals (15s each) -- useLiveData's interval
    // guards on document.hidden so no new fetches should fire.
    await act(async () => {
      vi.advanceTimersByTime(35_000);
      await Promise.resolve();
    });

    // No new fetches while hidden.
    expect(fetchCallCount).toBe(afterMount);

    // Restore visibility -- useLiveData fires a refetch immediately.
    Object.defineProperty(document, "hidden", { value: false, configurable: true, writable: true });

    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
      await Promise.resolve();
    });

    await waitFor(() => expect(fetchCallCount).toBeGreaterThan(afterMount), { timeout: 3000 });
  });

  it("stale-never-green: isStale suppresses green badge (shows amber 'stale')", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    // Fetch succeeds with live:true on the first call.
    global.fetch = vi.fn().mockImplementation(async () => ({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => liveDoc,
    })) as unknown as typeof fetch;

    const { container } = render(<LiveIndicator />);

    // Drain mount microtasks so the first fetch fires.
    await act(async () => {
      await Promise.resolve();
    });

    // Wait for the green state.
    await waitFor(() =>
      expect(screen.getByText(/RUNNING INDEPENDENTLY/i)).toBeTruthy(),
      { timeout: 3000 },
    );

    // Now make all subsequent fetches fail (simulate network loss).
    global.fetch = vi.fn().mockRejectedValue(new Error("network")) as unknown as typeof fetch;

    // Advance the age ticker past staleAfterSec (60s). The age ticker in
    // useLiveData runs every 1s and flips isStale when ageSec > staleAfterSec.
    await act(async () => {
      vi.advanceTimersByTime(65_000); // past 60s staleAfterSec
      await Promise.resolve();
    });

    // The banner must NOT be green when stale.
    // The stale-never-green rule in LiveIndicator degrades the effectiveTone to amber.
    const statusDiv = container.querySelector('[role="status"][aria-live]');
    expect(statusDiv).not.toBeNull();
    expect(statusDiv!.className).not.toMatch(/bg-tier-a\/10/);
    // The status div must have amber classes (the stale downgrade).
    expect(statusDiv!.className).toMatch(/amber/);
  });

  it("app/models/error.tsx exists (Next.js error boundary)", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const errorPath = join(here, "..", "..", "..", "app", "models", "error.tsx");
    const src = readFileSync(errorPath, "utf-8");
    // Must be a 'use client' boundary (Next.js error.tsx requirement).
    expect(src).toMatch(/"use client"/);
    // Must export a default function (the error component).
    expect(src).toMatch(/export default function/);
    // Must accept reset prop (required by Next.js error boundary contract).
    expect(src).toMatch(/reset/);
  });
});
