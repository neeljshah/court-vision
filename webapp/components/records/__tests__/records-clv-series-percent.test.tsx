import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import type { ClvSeries, ClvSeriesPoint } from "@/lib/types";
import { RecordsClvSeries } from "../RecordsClvSeries";

type ChartPoint = ClvSeriesPoint & { cumPct: number; index: number };
const chart = vi.hoisted(() => ({ data: [] as ChartPoint[] }));

// Capture the data and key actually supplied to Recharts. Invoke the component's
// own tooltip content with each plotted point; no private formatter is exported.
vi.mock("recharts", async () => {
  const { cloneElement } = await import("react");
  return {
    ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    LineChart: ({ data, children }: { data: ChartPoint[]; children: ReactNode }) => {
      chart.data = data;
      return <div data-testid="mock-line-chart">{children}</div>;
    },
    Line: ({ dataKey }: { dataKey: string }) => <div data-testid="plotted-data-key">{dataKey}</div>,
    XAxis: () => null,
    YAxis: () => null,
    ReferenceLine: () => null,
    Tooltip: ({ content }: { content: ReactElement }) => (
      <div>
        {chart.data.map((point, index) => (
          <div key={index}>
            {cloneElement(content, {
              active: true,
              payload: [{ value: point.cumPct, payload: point }],
            })}
          </div>
        ))}
      </div>
    ),
  };
});

afterEach(() => {
  cleanup();
  chart.data = [];
});

function point(value: number, overrides: Partial<ClvSeriesPoint> = {}): ClvSeriesPoint {
  return {
    ts: "2026-09-20T12:00:00Z",
    matchup: "Home vs Away",
    sport: "nba",
    clv_pct: value,
    cumulative_mean_clv_pct: value,
    beat_close: true,
    clv_is_proxy: false,
    ...overrides,
  };
}

function feed(points: ClvSeriesPoint[]): ClvSeries {
  return { status: "ok", count: points.length, series: points, honest_note: "No gradeable closes." };
}

describe("RecordsClvSeries already-percent cumulative values", () => {
  it.each([
    { value: 12.991798, expected: "+12.99%" },
    { value: 0.4, expected: "+0.40%" },
    { value: 0.008, expected: "+0.01%" },
    { value: -2.5, expected: "-2.50%" },
    { value: 0, expected: "+0.00%" },
  ])("keeps $value percent consistent in chart, endpoint and tooltip", ({ value, expected }) => {
    render(<RecordsClvSeries clvSeries={feed([point(value)])} />);
    expect(screen.getByTestId("plotted-data-key")).toHaveTextContent("cumPct");
    expect(chart.data[0].cumPct).toBe(value);
    expect(screen.getByTestId("clv-series-last-val")).toHaveTextContent(expected);
    expect(screen.getByTestId("clv-series-tooltip")).toHaveTextContent(`cum. CLV: ${expected}`);
  });

  it("keeps wire order, matchup, proxy markers and beat/missed/n/a labels", () => {
    const points = [
      point(0.4, { matchup: "First", ts: "2026-09-22", clv_is_proxy: true }),
      point(-2.5, { matchup: "Second", ts: "2026-09-20", beat_close: false }),
      point(12.991798, { matchup: "Third", ts: "2026-09-21", beat_close: null }),
    ];
    render(<RecordsClvSeries clvSeries={feed(points)} />);
    expect(chart.data.map((p) => p.matchup)).toEqual(["First", "Second", "Third"]);
    expect(chart.data.map((p) => p.index)).toEqual([1, 2, 3]);
    expect(chart.data.map((p) => p.ts)).toEqual(points.map((p) => p.ts));
    const tooltips = screen.getAllByTestId("clv-series-tooltip");
    expect(tooltips[0]).toHaveTextContent("First");
    expect(tooltips[0]).toHaveTextContent("this bet: beat (proxy)");
    expect(tooltips[1]).toHaveTextContent("Second");
    expect(tooltips[1]).toHaveTextContent("this bet: missed");
    expect(tooltips[2]).toHaveTextContent("Third");
    expect(tooltips[2]).toHaveTextContent("this bet: n/a");
    expect(screen.getByText("(some proxy closes)")).toBeInTheDocument();
    expect(chart.data.map((p) => p.cumPct)).toEqual(points.map((p) => p.cumulative_mean_clv_pct));
    expect(within(tooltips[2]).getByText("+12.99%")).toBeInTheDocument();
    expect(screen.getByTestId("clv-series-last-val")).toHaveTextContent("+12.99%");
  });

  it.each([
    { name: "empty", value: feed([]) },
    { name: "null", value: null },
    { name: "unavailable", value: { status: "unavailable" as const, reason: "Feed unavailable" } },
  ])("shows $name without fabricating a plotted value", ({ value }) => {
    render(<RecordsClvSeries clvSeries={value} nNoClose={2} />);
    expect(screen.getByTestId("clv-series-empty")).toHaveTextContent("INSUFFICIENT_DATA");
    expect(screen.getByText("2 bets logged, awaiting closing prices")).toBeInTheDocument();
    expect(screen.queryByTestId("clv-series-chart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("clv-series-last-val")).not.toBeInTheDocument();
    expect(chart.data).toEqual([]);
  });

  it("keeps a pending feed in the loading state without plotting a zero", () => {
    render(<RecordsClvSeries clvSeries={null} loading />);
    expect(screen.getByTestId("clv-series-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("clv-series-chart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("clv-series-last-val")).not.toBeInTheDocument();
    expect(chart.data).toEqual([]);
  });
});
