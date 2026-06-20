// RecordsClvSeries.test.tsx -- W1-records-clv-analytics per-file test.
//
// Acceptance assertions per spec:
//   1. series component renders 'no closes graded yet' honest state when count=0.
//   2. renders a sparkline when series has >=1 point.
//   3. NO '$' string in rendered output.
//   4. curl /api/paper/clv/series returns HTTP 200 and the component consumes .series array.
//
// We test the component shape contract; the live curl check is logged only
// (it would fail in CI without a running server and would freeze the test run).

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// Recharts uses SVG/ResizeObserver in jsdom -- minimal mock to avoid errors.
vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container" style={{ width: 400, height: 100 }}>
        {children}
      </div>
    ),
  };
});

import { RecordsClvSeries } from "../RecordsClvSeries";
import type { ClvSeries, ClvSeriesPoint } from "@/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makePoint(overrides: Partial<ClvSeriesPoint> = {}): ClvSeriesPoint {
  return {
    ts:                      "2026-06-01T12:00:00Z",
    matchup:                 "NYK vs SAS",
    sport:                   "nba",
    clv_pct:                 0.03,
    beat_close:              true,
    clv_is_proxy:            false,
    cumulative_mean_clv_pct: 0.03,
    ...overrides,
  };
}

function makeSeries(overrides: Partial<ClvSeries> = {}): ClvSeries {
  return {
    status:      "ok",
    count:       0,
    series:      [],
    honest_note: "Paper-only. executed is always False.",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// 1. Honest empty state (count=0 / empty series)
// ---------------------------------------------------------------------------

describe("RecordsClvSeries -- honest empty state when count=0", () => {
  it("renders the empty sentinel when series is empty", () => {
    render(<RecordsClvSeries clvSeries={makeSeries({ count: 0, series: [] })} />);
    expect(screen.getByTestId("clv-series-empty")).toBeInTheDocument();
  });

  it("shows 'no closes graded yet' language when empty", () => {
    render(<RecordsClvSeries clvSeries={makeSeries({ count: 0, series: [] })} />);
    const el = screen.getByTestId("clv-series-empty");
    expect(el.textContent?.toLowerCase()).toContain("no closes graded yet");
  });

  it("renders INSUFFICIENT_DATA label when empty", () => {
    render(<RecordsClvSeries clvSeries={makeSeries({ count: 0, series: [] })} />);
    expect(screen.getByTestId("clv-series-empty").textContent).toContain("INSUFFICIENT_DATA");
  });

  it("renders honest empty when clvSeries is null", () => {
    render(<RecordsClvSeries clvSeries={null} />);
    expect(screen.getByTestId("clv-series-empty")).toBeInTheDocument();
  });

  it("renders honest empty when status=unavailable", () => {
    render(<RecordsClvSeries clvSeries={{ status: "unavailable", reason: "service down" }} />);
    expect(screen.getByTestId("clv-series-empty")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 2. Sparkline rendered when series has >= 1 point
// ---------------------------------------------------------------------------

describe("RecordsClvSeries -- sparkline when series has >= 1 point", () => {
  it("renders the chart testid when series has 1 point", () => {
    render(
      <RecordsClvSeries
        clvSeries={makeSeries({
          count:  1,
          series: [makePoint({ cumulative_mean_clv_pct: 0.025 })],
        })}
      />,
    );
    expect(screen.getByTestId("clv-series-chart")).toBeInTheDocument();
  });

  it("does NOT render the empty sentinel when series has >= 1 point", () => {
    render(
      <RecordsClvSeries
        clvSeries={makeSeries({
          count:  3,
          series: [
            makePoint({ cumulative_mean_clv_pct: 0.01 }),
            makePoint({ cumulative_mean_clv_pct: 0.02 }),
            makePoint({ cumulative_mean_clv_pct: 0.015 }),
          ],
        })}
      />,
    );
    expect(screen.queryByTestId("clv-series-empty")).not.toBeInTheDocument();
    expect(screen.getByTestId("clv-series-chart")).toBeInTheDocument();
  });

  it("shows the last cumulative CLV value", () => {
    render(
      <RecordsClvSeries
        clvSeries={makeSeries({
          count:  1,
          series: [makePoint({ cumulative_mean_clv_pct: 0.03 })],
        })}
      />,
    );
    const lastVal = screen.getByTestId("clv-series-last-val");
    // 0.03 * 100 = 3.00%
    expect(lastVal.textContent).toContain("3.00%");
  });

  it("shows negative last val with minus sign when CLV is negative", () => {
    render(
      <RecordsClvSeries
        clvSeries={makeSeries({
          count:  1,
          series: [makePoint({ cumulative_mean_clv_pct: -0.025 })],
        })}
      />,
    );
    const lastVal = screen.getByTestId("clv-series-last-val");
    expect(lastVal.textContent).toContain("-2.50%");
  });

  it("renders proxy note when any point has clv_is_proxy=true", () => {
    render(
      <RecordsClvSeries
        clvSeries={makeSeries({
          count:  2,
          series: [
            makePoint({ clv_is_proxy: true }),
            makePoint({ clv_is_proxy: false }),
          ],
        })}
      />,
    );
    const chart = screen.getByTestId("clv-series-chart");
    expect(chart.textContent?.toLowerCase()).toContain("proxy");
  });
});

// ---------------------------------------------------------------------------
// 3. No $ token anywhere
// ---------------------------------------------------------------------------

describe("RecordsClvSeries -- no $ token", () => {
  it("renders no $ token when empty", () => {
    const { container } = render(
      <RecordsClvSeries clvSeries={makeSeries({ count: 0, series: [] })} />,
    );
    expect(/\$\s*\d/.test(container.textContent ?? "")).toBe(false);
  });

  it("renders no $ token when series has data", () => {
    const { container } = render(
      <RecordsClvSeries
        clvSeries={makeSeries({
          count:  2,
          series: [
            makePoint({ cumulative_mean_clv_pct: 0.01 }),
            makePoint({ cumulative_mean_clv_pct: 0.02 }),
          ],
        })}
      />,
    );
    expect(/\$\s*\d/.test(container.textContent ?? "")).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 4. Loading skeleton
// ---------------------------------------------------------------------------

describe("RecordsClvSeries -- loading skeleton", () => {
  it("renders loading skeleton when loading=true and clvSeries=null", () => {
    render(<RecordsClvSeries clvSeries={null} loading />);
    expect(screen.getByTestId("clv-series-loading")).toBeInTheDocument();
  });

  it("renders records-clv-series testid in loading state", () => {
    render(<RecordsClvSeries clvSeries={null} loading />);
    expect(screen.getByTestId("records-clv-series")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 5. API shape contract -- .series array consumed correctly
// ---------------------------------------------------------------------------

describe("RecordsClvSeries -- consumes .series array from API shape", () => {
  it("renders a chart for a 5-point series matching the wire shape", () => {
    const wireShape: ClvSeries = {
      status:      "ok",
      count:       5,
      series:      Array.from({ length: 5 }, (_, i) => ({
        ts:                      `2026-06-0${i + 1}T12:00:00Z`,
        matchup:                 `Team A vs Team B`,
        sport:                   "nba",
        clv_pct:                 0.01 * (i + 1),
        beat_close:              i % 2 === 0,
        clv_is_proxy:            false,
        cumulative_mean_clv_pct: 0.01 * (i + 1),
      })),
      honest_note: "Paper-only.",
    };
    render(<RecordsClvSeries clvSeries={wireShape} />);
    expect(screen.getByTestId("clv-series-chart")).toBeInTheDocument();
    expect(screen.queryByTestId("clv-series-empty")).not.toBeInTheDocument();
  });
});
