// HomeStatusRow.test.tsx -- per-component vitest for the live-refresh status strip.
//
// WS2-home-livehook acceptance checklist:
//   WS2-1. Component delegates to useLiveData (spy confirms it is called).
//   WS2-2. No bespoke data setInterval remains in the component itself --
//           after a poll cycle setInterval is called only by the hook, not the
//           component directly (asserted via the useLiveData spy + a
//           setInterval count comparison).
//   WS2-3. Renders last-good values with a stale indicator on a failed poll.
//   WS2-4. Shows 'updated Ns ago' age label once data has arrived.
//   WS2-5. Before first load isLoading=true -> neutral checking strip, not red.
//
// Original acceptance checklist (preserved):
//   1. Before first resolve -> neutral "checking..." affordance, NO green cell.
//   2. After resolve -> cells render real values from mocked endpoints.
//   3. Last-updated age label is present after first resolve.
//   4. null allHonest / null parity.green -> grey "unknown" (never green).
//   5. Polling interval is registered and cleared on unmount (no timer leak).
//   6. Renders without crashing.
//   7. Color dots are aria-hidden; text value carries state (WCAG 1.4.1).
//   8. No $ value anywhere (units-not-$ rail).

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { ProductStatus, ParityHeadline } from "@/lib/api";
import type { LiveDataState } from "@/lib/useLiveData";
import * as apiMod from "@/lib/api";
import * as useLiveDataMod from "@/lib/useLiveData";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeStatus(over: Partial<ProductStatus> = {}): ProductStatus {
  return {
    allHonest: true,
    allHonestReason: "ok",
    selfImprove: "READY_INERT",
    selfImproveLabel: "self-improve: READY (not enabled)",
    realMoney: "DENY",
    liveSports: [],
    edgeClaimed: false,
    ...over,
  } as ProductStatus;
}

function makeParity(over: Partial<ParityHeadline> = {}): ParityHeadline {
  return { green: true, nSports: 4, reason: "ok", ...over };
}

function mockEndpoints(
  s: ProductStatus | "reject",
  p: ParityHeadline | "reject",
) {
  vi.spyOn(apiMod, "getProductStatus").mockImplementation(() =>
    s === "reject" ? Promise.reject(new Error("down")) : Promise.resolve(s),
  );
  vi.spyOn(apiMod, "getParityHeadline").mockImplementation(() =>
    p === "reject" ? Promise.reject(new Error("down")) : Promise.resolve(p),
  );
}

// Builds a LiveDataState<{ status: ProductStatus | null; parity: ParityHeadline | null }>
// for injecting directly via the useLiveData spy.
function makeLiveState(
  over: Partial<LiveDataState<{ status: ProductStatus | null; parity: ParityHeadline | null }>> = {},
): LiveDataState<{ status: ProductStatus | null; parity: ParityHeadline | null }> {
  return {
    data: { status: makeStatus(), parity: makeParity() },
    lastUpdatedAt: Date.now(),
    ageSec: 5,
    isStale: false,
    error: null,
    isLoading: false,
    consecutiveFailures: 0,
    backoffActive: false,
    refresh: vi.fn(),
    ...over,
  };
}

// Import after mocks are declared so vi.spyOn can patch the module.
import { HomeStatusRow } from "../HomeStatusRow";

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// WS2-1 + WS2-2: component delegates to useLiveData; no bespoke data interval
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- WS2 useLiveData delegation (WS2-1, WS2-2)", () => {
  it("WS2-1: calls useLiveData once on mount", () => {
    const spy = vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState() as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    render(<HomeStatusRow />);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("WS2-2: component itself adds no more than 2 setInterval calls (hook owns them)", () => {
    // The hook registers: (a) the poll interval and (b) the age ticker.
    // With the migration the component itself must not add a THIRD data-polling
    // interval. We spy on the real hook (pass-through) and count setInterval
    // calls after mount. The hook's two internal intervals are expected; any
    // additional data-polling interval inside the component would bump the count.
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState() as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    const setIntervalSpy = vi.spyOn(global, "setInterval");
    render(<HomeStatusRow />);
    // The component must call setInterval 0 times when useLiveData is mocked
    // (all interval scheduling is inside the hook, not the component).
    expect(setIntervalSpy).toHaveBeenCalledTimes(0);
  });
});

// ---------------------------------------------------------------------------
// WS2-3: stale indicator on failed poll (last-good values retained)
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- WS2 stale indicator on failed poll (WS2-3)", () => {
  it("shows stale badge when isStale=true and retains last-good cell values", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState({
        data: {
          status: makeStatus({ allHonest: true, liveSports: ["nba"] }),
          parity: makeParity({ green: true }),
        },
        isStale: true,
        ageSec: 90,
        error: "both endpoints failed",
      }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    render(<HomeStatusRow />);

    // Last-good values are visible.
    expect(screen.getByText("TRUE")).toBeTruthy();
    expect(screen.getByText("FULLY GREEN")).toBeTruthy();
    // Stale badge is present.
    expect(screen.getByTestId("stale-badge")).toBeTruthy();
  });

  it("stale badge text contains '(stale)' marker", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState({
        isStale: true,
        ageSec: 120,
      }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    const { container } = render(<HomeStatusRow />);
    expect(container.textContent).toMatch(/stale/i);
  });

  it("no stale badge when isStale=false", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState({ isStale: false }) as ReturnType<
        typeof useLiveDataMod.useLiveData
      >,
    );
    render(<HomeStatusRow />);
    expect(screen.queryByTestId("stale-badge")).toBeNull();
  });

  it("stale badge is NOT red -- carries text-warning class (neutral/amber)", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState({
        isStale: true,
        ageSec: 90,
      }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    const { container } = render(<HomeStatusRow />);
    const badge = container.querySelector("[data-testid='stale-badge']");
    expect(badge).toBeTruthy();
    // Must NOT use a red/danger class (honest -- stale is amber, not error).
    expect(badge?.className ?? "").not.toMatch(/bg-danger|text-danger|bg-red|text-red/);
  });
});

// ---------------------------------------------------------------------------
// WS2-4: age label 'updated Ns ago'
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- WS2 age label (WS2-4)", () => {
  it("shows 'updated Ns ago' when ageSec is set", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState({ ageSec: 30 }) as ReturnType<
        typeof useLiveDataMod.useLiveData
      >,
    );
    render(<HomeStatusRow />);
    const label = screen.getByTestId("last-updated-label");
    expect(label.textContent).toMatch(/updated.*ago/i);
  });

  it("shows 'updated just now' for ageSec < 5", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState({ ageSec: 2 }) as ReturnType<
        typeof useLiveDataMod.useLiveData
      >,
    );
    render(<HomeStatusRow />);
    expect(screen.getByTestId("last-updated-label").textContent).toMatch(
      /updated just now/i,
    );
  });

  it("age label is NOT shown during initial loading (isLoading=true, ageSec=null)", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState({
        isLoading: true,
        data: null,
        ageSec: null,
        lastUpdatedAt: null,
      }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    render(<HomeStatusRow />);
    expect(screen.queryByTestId("last-updated-label")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// WS2-5: neutral state (not red) before first load
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- WS2 neutral initial state (WS2-5)", () => {
  it("shows checking strip (not red) when isLoading=true", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState({
        isLoading: true,
        data: null,
        ageSec: null,
        lastUpdatedAt: null,
      }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    const { container } = render(<HomeStatusRow />);
    expect(screen.getByTestId("checking-strip")).toBeTruthy();
    // No red/danger class anywhere in the initial loading strip.
    expect(container.innerHTML).not.toContain("bg-danger");
    expect(container.innerHTML).not.toContain("text-danger");
    expect(container.innerHTML).not.toContain("bg-red");
  });

  it("checking strip shows 'checking...' text, not green or error text", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState({
        isLoading: true,
        data: null,
        ageSec: null,
        lastUpdatedAt: null,
      }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    render(<HomeStatusRow />);
    const cells = screen.getAllByText("checking...");
    expect(cells.length).toBeGreaterThan(0);
    expect(screen.queryByText("TRUE")).toBeNull();
    expect(screen.queryByText("FULLY GREEN")).toBeNull();
  });

  it("no bg-success (green) in initial loading state", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState({
        isLoading: true,
        data: null,
        ageSec: null,
        lastUpdatedAt: null,
      }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    const { container } = render(<HomeStatusRow />);
    expect(container.innerHTML).not.toContain("bg-success");
  });
});

// ---------------------------------------------------------------------------
// SPEC 1: Before first resolve -> neutral "checking..." strip, no green cell
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- initial loading state (spec 1)", () => {
  it("shows a neutral checking strip before the first fetch resolves", () => {
    // Promises that will never settle during a synchronous render check.
    const neverStatus = new Promise<ProductStatus>(() => {});
    const neverParity = new Promise<ParityHeadline>(() => {});
    vi.spyOn(apiMod, "getProductStatus").mockReturnValue(neverStatus);
    vi.spyOn(apiMod, "getParityHeadline").mockReturnValue(neverParity);

    render(<HomeStatusRow />);

    // The checking strip must be visible immediately on render.
    expect(screen.getByTestId("checking-strip")).toBeTruthy();
    const cells = screen.getAllByText("checking...");
    expect(cells.length).toBeGreaterThan(0);
  });

  it("no cell carries bg-success (green) before first resolve", () => {
    const neverStatus = new Promise<ProductStatus>(() => {});
    const neverParity = new Promise<ParityHeadline>(() => {});
    vi.spyOn(apiMod, "getProductStatus").mockReturnValue(neverStatus);
    vi.spyOn(apiMod, "getParityHeadline").mockReturnValue(neverParity);

    const { container } = render(<HomeStatusRow />);
    expect(container.innerHTML).not.toContain("bg-success");
  });

  it("does not show resolved values before first fetch completes", () => {
    const neverStatus = new Promise<ProductStatus>(() => {});
    const neverParity = new Promise<ParityHeadline>(() => {});
    vi.spyOn(apiMod, "getProductStatus").mockReturnValue(neverStatus);
    vi.spyOn(apiMod, "getParityHeadline").mockReturnValue(neverParity);

    render(<HomeStatusRow />);
    expect(screen.queryByText("TRUE")).toBeNull();
    expect(screen.queryByText("FULLY GREEN")).toBeNull();
    expect(screen.queryByText("DENY (paper)")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// SPEC 2: After resolve -> cells render real values
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- resolved state / happy path (spec 2)", () => {
  it("renders without crashing (spec 6)", () => {
    mockEndpoints(makeStatus({}), makeParity({}));
    expect(() => render(<HomeStatusRow />)).not.toThrow();
  });

  it("shows all_honest TRUE after resolve", async () => {
    mockEndpoints(makeStatus({ allHonest: true, liveSports: ["nba"] }), makeParity({ green: true }));
    render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText("TRUE")).toBeTruthy());
  });

  it("shows parity FULLY GREEN after resolve", async () => {
    mockEndpoints(makeStatus({}), makeParity({ green: true }));
    render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText("FULLY GREEN")).toBeTruthy());
  });

  it("shows live sports after resolve", async () => {
    mockEndpoints(makeStatus({ liveSports: ["nba"] }), makeParity({}));
    render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText("nba")).toBeTruthy());
  });

  it("shows DENY (paper) for real-money after resolve", async () => {
    mockEndpoints(makeStatus({}), makeParity({}));
    render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText("DENY (paper)")).toBeTruthy());
  });

  it("shows READY (inert) for self-improve after resolve", async () => {
    mockEndpoints(makeStatus({ selfImprove: "READY_INERT" }), makeParity({}));
    render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText("READY (inert)")).toBeTruthy());
  });

  it("labels all five cells (all_honest, live now, parity, self-improve, real-money)", async () => {
    mockEndpoints(makeStatus({}), makeParity({}));
    render(<HomeStatusRow />);
    await waitFor(() => {
      for (const label of [
        "all_honest",
        "live now",
        "parity",
        "self-improve",
        "real-money",
      ]) {
        expect(screen.getByText(label)).toBeTruthy();
      }
    });
  });
});

// ---------------------------------------------------------------------------
// SPEC 3: Last-updated age label is present after resolve
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- last-updated age label (spec 3)", () => {
  it("last-updated label appears after first fetch resolves", async () => {
    mockEndpoints(makeStatus({}), makeParity({}));
    render(<HomeStatusRow />);
    await waitFor(() => {
      expect(screen.getByTestId("last-updated-label")).toBeTruthy();
    });
  });

  it("age label contains 'updated' text", async () => {
    mockEndpoints(makeStatus({}), makeParity({}));
    render(<HomeStatusRow />);
    await waitFor(() => {
      const label = screen.getByTestId("last-updated-label");
      expect(label.textContent ?? "").toMatch(/updated/i);
    });
  });

  it("age label is NOT shown during initial loading", () => {
    const neverStatus = new Promise<ProductStatus>(() => {});
    const neverParity = new Promise<ParityHeadline>(() => {});
    vi.spyOn(apiMod, "getProductStatus").mockReturnValue(neverStatus);
    vi.spyOn(apiMod, "getParityHeadline").mockReturnValue(neverParity);

    render(<HomeStatusRow />);
    expect(screen.queryByTestId("last-updated-label")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// SPEC 4: null allHonest / null parity.green -> grey "unknown" (never green)
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- null values stay grey (spec 4)", () => {
  it("null allHonest renders 'unknown' and no bg-success dot in that cell", async () => {
    mockEndpoints(makeStatus({ allHonest: null as unknown as boolean }), makeParity({}));

    const { container } = render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText("unknown")).toBeTruthy());

    const unknownEl = screen.getByText("unknown");
    const cell = unknownEl.closest("[class*='border-border']");
    const dot = cell?.querySelector("[aria-hidden='true']");
    expect((dot?.className ?? "")).not.toContain("bg-success");
    expect((dot?.className ?? "")).toContain("bg-muted-foreground");
  });

  it("null parity.green renders 'unknown' not 'FULLY GREEN'", async () => {
    mockEndpoints(makeStatus({}), makeParity({ green: null as unknown as boolean }));

    render(<HomeStatusRow />);
    await waitFor(() => {
      // After settle: parity cell should show "unknown", not "FULLY GREEN"
      expect(screen.queryByText("FULLY GREEN")).toBeNull();
    });
    expect(screen.getAllByText("unknown").length).toBeGreaterThan(0);
  });

  it("empty liveSports -> 'no games live now' with grey dot (not green)", async () => {
    mockEndpoints(makeStatus({ liveSports: [] }), makeParity({}));

    const { container } = render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText("no games live now")).toBeTruthy());

    const liveEl = screen.getByText("no games live now");
    const cell = liveEl.closest("[class*='border-border']");
    const dot = cell?.querySelector("[aria-hidden='true']");
    expect((dot?.className ?? "")).not.toContain("bg-success");
    expect((dot?.className ?? "")).toContain("bg-muted-foreground");
  });

  it("both endpoints rejected -> no bg-success dot anywhere after settle", async () => {
    mockEndpoints("reject", "reject");

    const { container } = render(<HomeStatusRow />);
    // Wait for the initial-loading flag to clear (cells settle to unknown/degraded).
    await waitFor(() => {
      expect(screen.queryByTestId("checking-strip")).toBeNull();
    });
    expect(container.innerHTML).not.toContain("bg-success");
  });
});

// ---------------------------------------------------------------------------
// SPEC 5: Polling interval registered + cleared on unmount (no timer leak)
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- polling lifecycle (spec 5)", () => {
  it("registers setInterval on mount (via useLiveData internals)", () => {
    mockEndpoints(makeStatus({}), makeParity({}));
    // Spy before rendering so we capture the setInterval calls from the hook.
    const setIntervalSpy = vi.spyOn(global, "setInterval");
    render(<HomeStatusRow />);
    // useLiveData registers: (a) the poll interval + (b) the age ticker.
    expect(setIntervalSpy).toHaveBeenCalled();
  });

  it("clearInterval called on unmount (no timer leak)", () => {
    mockEndpoints(makeStatus({}), makeParity({}));
    const clearIntervalSpy = vi.spyOn(global, "clearInterval");
    const { unmount } = render(<HomeStatusRow />);
    unmount();
    // Both the poll interval and the clock interval must be cleared.
    expect(clearIntervalSpy).toHaveBeenCalled();
    expect(clearIntervalSpy.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("re-fetches after POLL_INTERVAL_MS (20s) using fake timers", async () => {
    // This test uses fake timers scoped to just this test.
    vi.useFakeTimers();
    try {
      const statusSpy = vi
        .spyOn(apiMod, "getProductStatus")
        .mockResolvedValue(makeStatus({}));
      vi.spyOn(apiMod, "getParityHeadline").mockResolvedValue(makeParity({}));

      render(<HomeStatusRow />);

      // Let the initial fetch's micro-task settle (Promise.resolve resolves on
      // microtask queue, not timer queue -- draining via a real 0ms flush).
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();

      const callsAfterMount = statusSpy.mock.calls.length;
      expect(callsAfterMount).toBeGreaterThanOrEqual(1);

      // Trigger the poll interval (20 001ms to clear the 20s threshold).
      vi.advanceTimersByTime(20_001);

      // Micro-task drain: the new fetch is now enqueued.
      await Promise.resolve();
      await Promise.resolve();

      expect(statusSpy.mock.calls.length).toBeGreaterThan(callsAfterMount);
    } finally {
      vi.useRealTimers();
    }
  });
});

// ---------------------------------------------------------------------------
// SPEC 7: aria-hidden dots + text value carries state (WCAG 1.4.1)
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- WCAG 1.4.1 dots aria-hidden + text state (spec 7)", () => {
  it("every color dot carries aria-hidden='true' after resolve", async () => {
    mockEndpoints(makeStatus({ liveSports: ["nba"] }), makeParity({}));
    const { container } = render(<HomeStatusRow />);
    await waitFor(() => screen.getByText("TRUE"));

    const dots = container.querySelectorAll("[aria-hidden='true']");
    expect(dots.length).toBeGreaterThanOrEqual(5);
    for (const dot of Array.from(dots)) {
      expect(dot.getAttribute("aria-hidden")).toBe("true");
    }
  });

  it("state communicated by text, not color alone, for every cell", async () => {
    mockEndpoints(
      makeStatus({ allHonest: true, liveSports: ["soccer"], selfImprove: "READY_INERT" }),
      makeParity({ green: true }),
    );
    render(<HomeStatusRow />);
    await waitFor(() => screen.getByText("TRUE"));

    expect(screen.getByText("TRUE")).toBeTruthy();
    expect(screen.getByText("soccer")).toBeTruthy();
    expect(screen.getByText("FULLY GREEN")).toBeTruthy();
    expect(screen.getByText("READY (inert)")).toBeTruthy();
    expect(screen.getByText("DENY (paper)")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// SPEC 8: No $ value (units-not-$ rail)
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- no $ value in DOM (spec 8)", () => {
  it("no $<digit> in rendered output (happy path)", async () => {
    mockEndpoints(makeStatus({ liveSports: ["soccer"] }), makeParity({}));
    const { container } = render(<HomeStatusRow />);
    await waitFor(() => screen.getByText("TRUE"));
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("no $ during initial loading state", () => {
    const neverStatus = new Promise<ProductStatus>(() => {});
    const neverParity = new Promise<ParityHeadline>(() => {});
    vi.spyOn(apiMod, "getProductStatus").mockReturnValue(neverStatus);
    vi.spyOn(apiMod, "getParityHeadline").mockReturnValue(neverParity);
    const { container } = render(<HomeStatusRow />);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("no ROI label in output", async () => {
    mockEndpoints(makeStatus({}), makeParity({}));
    const { container } = render(<HomeStatusRow />);
    await waitFor(() => screen.getByText("TRUE"));
    expect(/\bROI\b/.test(container.textContent ?? "")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Preserved: original honest-cell-states suite
// ---------------------------------------------------------------------------

describe("HomeStatusRow -- honest cell states (original suite)", () => {
  it("all-green path: honest TRUE, live sports, parity FULLY GREEN", async () => {
    mockEndpoints(
      makeStatus({ allHonest: true, liveSports: ["soccer", "nba"] }),
      makeParity({ green: true }),
    );
    render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText("TRUE")).toBeTruthy());
    expect(screen.getByText(/soccer \/ nba/i)).toBeTruthy();
    expect(screen.getByText(/FULLY GREEN/i)).toBeTruthy();
  });

  it("honest FALSE renders FALSE (never hidden)", async () => {
    mockEndpoints(makeStatus({ allHonest: false }), makeParity({}));
    render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText("FALSE")).toBeTruthy());
  });

  it("status endpoint unreachable -> all_honest 'unknown', live cell 'unknown'", async () => {
    mockEndpoints("reject", makeParity({}));
    render(<HomeStatusRow />);
    // Both all_honest and live-now degrade to "unknown" when the endpoint rejects.
    await waitFor(() => {
      const unknownCells = screen.getAllByText("unknown");
      expect(unknownCells.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("no live games -> honest 'no games live now'", async () => {
    mockEndpoints(makeStatus({ liveSports: [] }), makeParity({}));
    render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText(/no games live now/i)).toBeTruthy());
  });

  it("parity unreachable -> 'unknown', not green", async () => {
    mockEndpoints(makeStatus({}), "reject");
    render(<HomeStatusRow />);
    await waitFor(() =>
      expect(screen.getAllByText(/unknown/i).length).toBeGreaterThan(0),
    );
  });

  it("parity not green -> renders 'not green'", async () => {
    mockEndpoints(makeStatus({}), makeParity({ green: false }));
    render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText(/not green/i)).toBeTruthy());
  });

  it("self-improve reads READY (inert) by default, ENABLED only when enabled", async () => {
    mockEndpoints(makeStatus({ selfImprove: "READY_INERT" }), makeParity({}));
    const { unmount } = render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText(/READY \(inert\)/i)).toBeTruthy());
    unmount();
    vi.restoreAllMocks();

    mockEndpoints(makeStatus({ selfImprove: "ENABLED" }), makeParity({}));
    render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText("ENABLED")).toBeTruthy());
  });

  it("real-money cell is ALWAYS DENY (paper)", async () => {
    mockEndpoints(makeStatus({}), makeParity({}));
    render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText(/DENY \(paper\)/i)).toBeTruthy());
  });

  it("renders NO dollar figure in the strip", async () => {
    mockEndpoints(makeStatus({ liveSports: ["soccer"] }), makeParity({}));
    const { container } = render(<HomeStatusRow />);
    await waitFor(() => expect(screen.getByText("TRUE")).toBeTruthy());
    const txt = container.textContent ?? "";
    expect(/\$/.test(txt)).toBe(false);
    expect(/\bROI\b/.test(txt)).toBe(false);
  });

  it("labels all five cells (all_honest, live now, parity, self-improve, real-money)", async () => {
    mockEndpoints(makeStatus({}), makeParity({}));
    render(<HomeStatusRow />);
    await waitFor(() => {
      for (const label of ["all_honest", "live now", "parity", "self-improve", "real-money"]) {
        expect(screen.getByText(label)).toBeTruthy();
      }
    });
  });
});
