// EvidenceTrendPanel.test.tsx -- empty/short/normal states. Mocks fetchHonest's
// underlying fetch so no real disk I/O / network.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { EvidenceTrendPanel } from "@/components/paper/EvidenceTrendPanel";

// recharts' ResponsiveContainer (used by Sparkline) needs ResizeObserver -- jsdom
// has none; a minimal no-op stub is enough for these render-only assertions.
// Direct assignment (not vi.stubGlobal) so afterEach's unstubAllGlobals -- which
// must clear the per-test fetch stubs -- doesn't strip it after the first test.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as { ResizeObserver?: unknown }).ResizeObserver = ResizeObserverStub;

function mockFetchOnce(body: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok,
      status: ok ? 200 : 503,
      headers: { get: () => "application/json" },
      json: async () => body,
    }),
  );
}

describe("EvidenceTrendPanel", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the honest accumulating state when the series is empty/unavailable", async () => {
    mockFetchOnce(
      { status: "unavailable", series_by_market: {}, latest: {}, n_vintages: 0, as_of: null },
      false,
    );
    render(<EvidenceTrendPanel />);
    await waitFor(() =>
      expect(screen.getByTestId("evidence-trend-short-series")).toHaveTextContent(
        /evidence accumulating/i,
      ),
    );
  });

  it("shows a per-market short-series note when a market has < 3 daily points", async () => {
    mockFetchOnce({
      status: "ok",
      series_by_market: {
        moneyline: [{ date: "2026-07-15", median_clv_pct: 1.2, n: 4 }],
      },
      latest: { moneyline: { median_clv_pct: 1.2, n: 4 } },
      n_vintages: 2,
      as_of: "2026-07-15T12:00:00Z",
    });
    render(<EvidenceTrendPanel />);
    await waitFor(() =>
      expect(screen.getByTestId("evidence-trend-market-short-moneyline")).toHaveTextContent(
        /trend after 3\+ days/i,
      ),
    );
    expect(screen.getByTestId("evidence-trend-row-moneyline")).toHaveTextContent("+1.20%");
  });

  it("renders a sparkline once a market has 3+ daily points", async () => {
    mockFetchOnce({
      status: "ok",
      series_by_market: {
        moneyline: [
          { date: "2026-07-13", median_clv_pct: 0.5, n: 3 },
          { date: "2026-07-14", median_clv_pct: 1.0, n: 4 },
          { date: "2026-07-15", median_clv_pct: 1.5, n: 5 },
        ],
      },
      latest: { moneyline: { median_clv_pct: 1.5, n: 5 } },
      n_vintages: 3,
      as_of: "2026-07-15T12:00:00Z",
    });
    render(<EvidenceTrendPanel />);
    const row = await screen.findByTestId("evidence-trend-row-moneyline");
    expect(row).toHaveTextContent("+1.50%");
    expect(row.querySelector(".recharts-responsive-container")).toBeTruthy();
    expect(screen.queryByTestId("evidence-trend-market-short-moneyline")).toBeNull();
  });
});
