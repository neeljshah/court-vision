/**
 * App.tsx integration smoke tests.
 *
 * Strategy:
 * - vi.stubGlobal("fetch") returns a small BoardResponse whose sport field is
 *   echoed from the request URL so the useBoard sport-match guard passes.
 * - getBoundingClientRect / offsetHeight / clientHeight are patched to non-zero
 *   so @tanstack/react-virtual renders rows in jsdom (same shim as BoardTable.test).
 * - vi.useFakeTimers({ shouldAdvanceTime: true }) prevents the 25s polling
 *   interval from firing during assertions; restored in afterEach.
 * - findBy / waitFor are used throughout -- no fixed sleeps.
 */

import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach, beforeAll } from "vitest";
import type { BoardResponse, BoardRow, Sport } from "@/types/board";
import App from "@/App";

// ---------------------------------------------------------------------------
// jsdom shims -- matchMedia + virtualizer dimensions
// jsdom does not implement window.matchMedia; useTheme calls it during the
// useState initializer so it must be present before the first render.
// ---------------------------------------------------------------------------
beforeAll(() => {
  // matchMedia stub: always reports light-mode preference, no-op listener.
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }

  const origGetBCR = Element.prototype.getBoundingClientRect;
  Element.prototype.getBoundingClientRect = function () {
    const real = origGetBCR.call(this);
    return {
      ...real,
      height: real.height || 1200,
      width: real.width || 800,
      top: real.top,
      left: real.left,
      right: real.right || 800,
      bottom: real.bottom || 1200,
      x: real.x,
      y: real.y,
      toJSON: real.toJSON ?? (() => ({})),
    };
  };
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get() { return 1200; },
  });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get() { return 1200; },
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    get() { return 800; },
  });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get() { return 800; },
  });
});

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

function makeRow(sport: Sport, state: BoardRow["state"], idx: number): BoardRow {
  return {
    sport,
    league: sport === "mlb" ? "mlb" : sport,
    state,
    start_time: new Date(Date.now() + idx * 60_000).toISOString(),
    home: `HomeTeam${idx}`,
    away: `AwayTeam${idx}`,
    home_score: state === "post" ? 4 : null,
    away_score: state === "post" ? 2 : null,
    clock_text: state === "in" ? "T7" : null,
    win_home: 0.6,
    win_away: 0.4,
    draw: null,
    total: 8.5,
    market_odds: null,
    provider: null,
    source: "market",
    market_implied: true,
    note: null,
  };
}

/** Build a BoardResponse whose sport matches the one parsed from a fetch URL. */
function makeResponse(sport: Sport): BoardResponse {
  return {
    sport,
    leagues: null,
    generated_at: new Date().toISOString(),
    rows: [
      makeRow(sport, "in", 0),   // live
      makeRow(sport, "pre", 1),  // upcoming
      makeRow(sport, "post", 2), // finished
    ],
  };
}

/** Parse sport from the URL string (/api/board?sport=xxx). Defaults to "mlb". */
function sportFromUrl(url: string): Sport {
  try {
    // url is a relative path like "/api/board?sport=soccer"; anchor to origin.
    const full = new URL(url, "http://localhost");
    const s = full.searchParams.get("sport");
    if (s === "mlb" || s === "soccer" || s === "tennis") return s;
  } catch {
    // ignore parse errors
  }
  return "mlb";
}

// ---------------------------------------------------------------------------
// Per-test setup / teardown
// ---------------------------------------------------------------------------

let fetchSpy: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });

  fetchSpy = vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : (input as Request).url;
    const sport = sportFromUrl(url);
    const body = JSON.stringify(makeResponse(sport));
    return Promise.resolve(
      new Response(body, {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
  });

  vi.stubGlobal("fetch", fetchSpy);
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("App integration smoke tests", () => {
  it("1. renders the header 'Live Board' and the footer disclaimer after initial load", async () => {
    render(<App />);

    // Header is synchronous -- present immediately.
    expect(screen.getByRole("heading", { name: /live board/i })).toBeInTheDocument();

    // Disclaimer renders twice (banner + footer); getAllByText handles both.
    await waitFor(() => {
      expect(screen.getAllByText(/no \$ edge claimed/i).length).toBeGreaterThan(0);
    });
  });

  it("2. a team name from the fixture appears after load -- proves virtualized list renders", async () => {
    render(<App />);

    // HomeTeam0 is the live row returned for every sport.
    // Multiple virtual items may render the same name; getAllByText tolerates duplicates.
    await waitFor(() => {
      expect(screen.getAllByText(/HomeTeam0/i).length).toBeGreaterThan(0);
    });
  });

  it("3. all three sport tabs are present; clicking Soccer triggers a fetch with sport=soccer", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) });
    render(<App />);

    // Wait for first load so tabs are enabled (multiple virtual items may share the name).
    await waitFor(() => {
      expect(screen.getAllByText(/HomeTeam0/i).length).toBeGreaterThan(0);
    });

    // All three tabs must be present.
    expect(screen.getByRole("tab", { name: /mlb/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /soccer/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /tennis/i })).toBeInTheDocument();

    const callsBefore = fetchSpy.mock.calls.length;

    await act(async () => {
      await user.click(screen.getByRole("tab", { name: /soccer/i }));
    });

    // A new fetch must fire whose URL contains sport=soccer.
    await waitFor(() => {
      const newCalls = fetchSpy.mock.calls.slice(callsBefore);
      const hasSoccer = newCalls.some((args) => {
        const url = typeof args[0] === "string" ? args[0] : String(args[0]);
        return url.includes("sport=soccer");
      });
      expect(hasSoccer).toBe(true);
    });
  });

  it("4. legend trigger is present; clicking it opens the dialog with in-corpus text", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime.bind(vi) });
    render(<App />);

    // The trigger button is rendered synchronously as part of the controls row.
    const trigger = await screen.findByRole("button", { name: /how to read/i });
    expect(trigger).toBeInTheDocument();

    // Dialog must not be open yet.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await act(async () => {
      await user.click(trigger);
    });

    // After click the Radix portal mounts -- find "in-corpus" inside it.
    await waitFor(() => {
      const dialog = screen.getByRole("dialog");
      expect(dialog).toBeInTheDocument();
      // in-corpus text should appear within the dialog content.
      expect(screen.getAllByText(/in-corpus/i).length).toBeGreaterThan(0);
    });
  });
});
