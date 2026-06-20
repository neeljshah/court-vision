// empty-state.test.tsx -- WS5 acceptance tests: honest empty state for /paper-trading.
//
// Acceptance criteria (WS5):
//   * With empty PM trail (total_pm=0), page shows the explicit
//     "no live PM game markets right now" message -- not a blank panel.
//   * Real-money DENY banner is always present.
//   * No fabricated rows (no venue-tile, no pm-trail-table rows) when trail is empty.
//   * executed=false reflected in empty-state note text.
//   * No dollar-amount in rendered output (units only -- honesty rail).
//
// Lane: frontend (webapp/**). NEVER touches human-gated paths.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

// Stub PmTrailTable so we can assert it renders no rows (table-ready with no children).
vi.mock("@/components/paper_pm/PmTrailTable", () => ({
  PmTrailTable: ({
    rows,
    loading,
  }: {
    rows?: unknown[];
    loading?: boolean;
  }) => (
    <div data-testid="pm-trail-table" data-row-count={rows?.length ?? 0}>
      {loading ? "table-loading" : `table-ready:${rows?.length ?? 0}-rows`}
    </div>
  ),
}));

// Stub PaperTrailSettled -- the real settled book component (deep deps, tested separately).
vi.mock("@/components/paper_pm/PaperTrailSettled", () => ({
  PaperTrailSettled: ({ loading, rows }: { loading?: boolean; rows?: unknown[] }) => (
    <div data-testid="paper-trail-settled" data-loading={String(!!loading)} data-rows={String((rows ?? []).length)}>
      {loading ? "settled-loading" : "settled-ready"}
    </div>
  ),
}));

import * as p5api from "@/lib/p5api";

const EMPTY_CLV: p5api.ClvScoreboard = {
  n_bets: 0,
  pct_beat_close: null,
  mean_clv_pct: null,
  by_sport: null,
  clv_is_proxy: false,
};

const EMPTY_PAPER_TRAIL = {
  status: "ok",
  count: 0,
  trail: [] as p5api.PaperTrailRow[],
};

// mockApiEmpty -- canonical WS5 scenario: total_pm=0, no trades, count=0.
function mockApiEmpty() {
  vi.spyOn(p5api.api, "getPaperTrail").mockResolvedValue(EMPTY_PAPER_TRAIL as never);
  vi.spyOn(p5api.api, "pmTrail").mockResolvedValue(
    { status: "ok", generated_at: null, trades: [], count: 0 } as never,
  );
  vi.spyOn(p5api.api, "getPaperClv").mockResolvedValue(EMPTY_CLV as never);
}

// mockApiPending -- still fetching; nothing resolved yet.
function mockApiPending() {
  vi.spyOn(p5api.api, "getPaperTrail").mockReturnValue(new Promise(() => {}));
  vi.spyOn(p5api.api, "pmTrail").mockReturnValue(new Promise(() => {}));
  vi.spyOn(p5api.api, "getPaperClv").mockReturnValue(new Promise(() => {}));
}

afterEach(() => vi.restoreAllMocks());

async function renderPage() {
  const { default: PaperTradingPage } = await import("../page");
  return render(<PaperTradingPage />);
}

// ---------------------------------------------------------------------------
// WS5 -- honest empty state: "no live PM game markets right now"
// ---------------------------------------------------------------------------

describe("/paper-trading WS5 -- honest empty state (total_pm=0)", () => {
  it("empty panel with testid no-paper-trades is present when total_pm=0", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument(),
    );
  });

  it("renders the explicit 'no live PM game markets right now' message", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByTestId("pm-empty-pm-game-markets").textContent,
      ).toMatch(/no live PM game markets right now/i),
    );
  });

  it("empty state has role=status so screen readers announce it", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      expect(el.getAttribute("role")).toBe("status");
    });
  });

  it("empty state aria-label confirms 'no live PM game markets'", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByLabelText("No live PM game markets right now"),
      ).toBeInTheDocument(),
    );
  });

  it("empty state mentions 'Executed: false' (no real trade was placed)", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      expect(el.textContent).toMatch(/executed.*false/i);
    });
  });

  it("empty state mentions 'Real-money: DENY'", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      expect(el.textContent).toMatch(/real-money.*deny/i);
    });
  });

  it("no-paper-trades is absent when loading (not yet resolved)", async () => {
    mockApiPending();
    await renderPage();
    // While pending, isEmpty=false because pmTrail is null, so no-paper-trades must be absent.
    expect(screen.queryByTestId("no-paper-trades")).toBeNull();
  });

  it("pm-empty-pm-game-markets element is absent while loading", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.queryByTestId("pm-empty-pm-game-markets")).toBeNull();
  });

  it("empty state does not carry danger/red styling", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() => {
      const el = screen.getByTestId("no-paper-trades");
      expect(el.className).not.toMatch(/text-red/);
      expect(el.className).not.toMatch(/text-danger/);
      expect(el.className).not.toMatch(/text-destructive/);
    });
  });
});

// ---------------------------------------------------------------------------
// WS5 -- real-money DENY banner always present (empty state & loading state)
// ---------------------------------------------------------------------------

describe("/paper-trading WS5 -- real-money DENY banner (empty state)", () => {
  it("DENY banner is present when total_pm=0", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument(),
    );
  });

  it("DENY banner contains 'DENY' text when total_pm=0", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByTestId("real-money-deny-banner").textContent,
      ).toMatch(/DENY/),
    );
  });

  it("DENY banner contains 'Real-money' when total_pm=0", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByTestId("real-money-deny-banner").textContent,
      ).toMatch(/real-money/i),
    );
  });

  it("DENY banner aria-label correct when total_pm=0", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByLabelText("Real money is DENIED -- paper mode only"),
      ).toBeInTheDocument(),
    );
  });

  it("DENY banner is present during loading state (before data arrives)", async () => {
    mockApiPending();
    await renderPage();
    expect(screen.getByTestId("real-money-deny-banner")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// WS5 -- no fabricated rows when PM trail is empty
// ---------------------------------------------------------------------------

describe("/paper-trading WS5 -- no fabricated rows when total_pm=0", () => {
  it("pm-trail-table renders 0 rows when trail is empty", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() => {
      const table = screen.getByTestId("pm-trail-table");
      expect(table.getAttribute("data-row-count")).toBe("0");
    });
  });

  it("no venue-tile is rendered when total_pm=0 (no fabricated venue rows)", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument(),
    );
    expect(screen.queryAllByTestId("venue-tile")).toHaveLength(0);
  });

  it("tally tiles all show 0 (no fabricated counts) when total_pm=0", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("tally-open").textContent).toBe("0");
      expect(screen.getByTestId("tally-settled").textContent).toBe("0");
      expect(screen.getByTestId("tally-win").textContent).toBe("0");
      expect(screen.getByTestId("tally-loss").textContent).toBe("0");
      expect(screen.getByTestId("tally-push").textContent).toBe("0");
    });
  });

  it("units-staked tile shows 0.00 (no fabricated stakes) when total_pm=0", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("tally-units-staked").textContent).toBe("0.00"),
    );
  });

  it("no dollar-amount ($N) in rendered output when total_pm=0 (honesty rail)", async () => {
    mockApiEmpty();
    const { container } = await renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument(),
    );
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("pm-total-count shows 'No PM markets' text when count=0", async () => {
    mockApiEmpty();
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByTestId("pm-total-count").textContent,
      ).toMatch(/no PM markets/i),
    );
  });
});
