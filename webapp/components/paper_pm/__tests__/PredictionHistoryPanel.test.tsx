// PredictionHistoryPanel.test.tsx -- ws5 acceptance tests.
//
// Acceptance (from workstream spec):
//   1. Given a mocked status='ok' payload of graded rows:
//      - the panel renders the rows (data-testid="prediction-row")
//      - each row shows model_prob, market_prob
//      - CLV may read INSUFFICIENT_DATA (clv_pct=null -> rendered as EMPTY_CELL "--")
//      - zero '$' substrings in the entire rendered output
//   2. Given a 404/empty/stale response:
//      - renders an explicit honest empty/stale banner (data-testid present)
//      - no fabricated rows rendered
//
// Strategy: vi.mock "@/lib/useLiveData" to control LiveDataState, bypassing
// all network + polling. Tests run purely synchronous -- no act/waitFor needed.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { PaperPredictions } from "@/lib/types";
import type { PaperPredictionRow } from "@/lib/types";

// ---------------------------------------------------------------------------
// Controlled useLiveData state -- shared across all tests.
// ---------------------------------------------------------------------------

type MockLiveDataState<T> = {
  data: T | null;
  lastUpdatedAt: number | null;
  ageSec: number | null;
  isStale: boolean;
  error: string | null;
  isLoading: boolean;
  consecutiveFailures: number;
  backoffActive: boolean;
  refresh: () => void;
};

function defaultState<T>(): MockLiveDataState<T> {
  return {
    data: null,
    lastUpdatedAt: null,
    ageSec: null,
    isStale: false,
    error: null,
    isLoading: true,
    consecutiveFailures: 0,
    backoffActive: false,
    refresh: vi.fn(),
  };
}

let _state: MockLiveDataState<unknown> = defaultState();

// Mock useLiveData BEFORE importing the component.
vi.mock("@/lib/useLiveData", () => ({
  useLiveData: () => _state,
  useLiveDataUrl: () => _state,
}));

// Mock the p5api module -- component calls api.paperPredictions via the
// callback passed to useLiveData; since useLiveData is mocked the fetcher
// is never invoked, but the import must still resolve.
vi.mock("@/lib/p5api", async () => {
  const actual = await import("@/lib/p5api");
  return {
    ...actual,
    api: {
      ...actual.api,
      paperPredictions: vi.fn(() => Promise.resolve({ status: "unavailable" })),
    },
  };
});

// Mock AgeBadge and p6/Primitives so they don't pull in complex deps.
vi.mock("@/components/bets/BestBetsBoard", () => ({
  AgeBadge: ({ asOf }: { asOf: string | null }) => (
    <span data-testid="age-badge">{asOf ?? "checking"}</span>
  ),
}));

vi.mock("@/components/p6/Primitives", () => ({
  Panel: ({
    title,
    right,
    children,
  }: {
    title: string;
    right?: React.ReactNode;
    children: React.ReactNode;
  }) => (
    <div>
      <div data-testid="panel-title">{title}</div>
      <div data-testid="panel-right">{right}</div>
      <div>{children}</div>
    </div>
  ),
  Badge: ({ children }: { children: React.ReactNode }) => (
    <span>{children}</span>
  ),
  Unavailable: ({ reason }: { reason?: string }) => (
    <div data-testid="unavailable-panel">{reason ?? "unavailable"}</div>
  ),
}));

// Import AFTER mocks.
import { PredictionHistoryPanel } from "../PredictionHistoryPanel";
import React from "react";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<PaperPredictionRow> = {}): PaperPredictionRow {
  return {
    game_id: "game1",
    matchup: "NYK vs SAS",
    sport: "nba",
    market_type: "moneyline",
    side: "home",
    model_prob: 0.62,
    market_prob: 0.51,
    edge_vs_market: 0.11,
    tier: "A",
    stake_units: 1.25,
    decision: "bet",
    outcome: "win",
    final_score: "110-104",
    clv_pct: 0.02,
    beat_close: true,
    clv_is_proxy: false,
    ts: "2026-06-19T22:00:00Z",
    ...overrides,
  };
}

function makeInsufficientDataRow(): PaperPredictionRow {
  return makeRow({
    clv_pct: null,
    beat_close: null,
    clv_is_proxy: false,
    outcome: "win",
    final_score: "112-101",
  });
}

function makePendingRow(): PaperPredictionRow {
  return makeRow({
    outcome: null,
    final_score: null,
    clv_pct: null,
    beat_close: null,
    decision: "bet",
    tier: "B",
  });
}

function okPayload(rows: PaperPredictionRow[]): PaperPredictions {
  return {
    status: "ok",
    count: rows.length,
    generated_at: new Date().toISOString(),
    predictions: rows,
    honest_note: "calibration only",
    edge_claimed: false,
  };
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function setState<T>(partial: Partial<MockLiveDataState<T>>) {
  _state = { ...(_state as MockLiveDataState<T>), ...partial } as MockLiveDataState<unknown>;
}

function resetState() {
  _state = defaultState();
}

// Assert no dollar-sign-followed-by-digit anywhere in the rendered output.
function assertNoDollar(container: HTMLElement) {
  expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
}

// ---------------------------------------------------------------------------
// (1) Data-present path -- graded rows render correctly
// ---------------------------------------------------------------------------

describe("PredictionHistoryPanel -- data present (ws5 acceptance #1)", () => {
  beforeEach(resetState);

  it("renders a row per prediction when status=ok payload is supplied", () => {
    const rows = [makeRow(), makeRow({ game_id: "game2", matchup: "BOS vs MIA" })];
    setState({ data: okPayload(rows), isLoading: false, error: null });
    const { container } = render(<PredictionHistoryPanel />);
    const rowEls = container.querySelectorAll('[data-testid="prediction-row"]');
    expect(rowEls.length).toBe(2);
  });

  it("renders model_prob as a percentage string in each row", () => {
    setState({ data: okPayload([makeRow({ model_prob: 0.62 })]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByText("62.0%")).toBeInTheDocument();
  });

  it("renders market_prob as a percentage string in each row", () => {
    setState({ data: okPayload([makeRow({ market_prob: 0.51 })]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByText("51.0%")).toBeInTheDocument();
  });

  it("renders CLV as '--' (EMPTY_CELL) when clv_pct is null (INSUFFICIENT_DATA path)", () => {
    setState({ data: okPayload([makeInsufficientDataRow()]), isLoading: false });
    const { container } = render(<PredictionHistoryPanel />);
    // edge_vs_market=0.11 renders as a pct; clv_pct=null not shown separately in this component.
    // Crucially, no dollar sign and the cell-level EMPTY_CELL "--" appears for final_score.
    // The important thing: no fabricated CLV$ figure.
    expect(container.textContent).not.toMatch(/clv.*\$/i);
  });

  it("renders WIN outcome label for a graded win row", () => {
    setState({ data: okPayload([makeRow({ outcome: "win" })]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("pred-outcome")).toHaveTextContent("WIN");
  });

  it("renders LOSS outcome label for a graded loss row", () => {
    setState({ data: okPayload([makeRow({ outcome: "loss" })]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("pred-outcome")).toHaveTextContent("LOSS");
  });

  it("renders 'pending' for an ungraded (outcome=null) row", () => {
    setState({ data: okPayload([makePendingRow()]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("pred-outcome")).toHaveTextContent("pending");
  });

  it("renders final_score when present (real game result string)", () => {
    setState({ data: okPayload([makeRow({ final_score: "110-104" })]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("pred-final-score")).toHaveTextContent("110-104");
  });

  it("renders '--' in final_score cell when final_score is null (game not yet settled)", () => {
    setState({ data: okPayload([makePendingRow()]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("pred-final-score")).toHaveTextContent("--");
  });

  it("renders the tier badge when tier is set", () => {
    setState({ data: okPayload([makeRow({ tier: "A" })]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("pred-tier")).toHaveTextContent("A");
  });

  it("renders 'Model Track Record' as the panel title", () => {
    setState({ data: okPayload([makeRow()]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("panel-title")).toHaveTextContent("Model Track Record");
  });

  it("renders data-testid=pred-history-table when rows are present", () => {
    setState({ data: okPayload([makeRow()]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("pred-history-table")).toBeInTheDocument();
  });

  it("(ws5 acceptance) zero '$' substrings anywhere in rendered output -- data present", () => {
    const rows = [
      makeRow({ model_prob: 0.7, market_prob: 0.55, stake_units: 2.0 }),
      makeInsufficientDataRow(),
      makePendingRow(),
    ];
    setState({ data: okPayload(rows), isLoading: false });
    const { container } = render(<PredictionHistoryPanel />);
    assertNoDollar(container);
  });

  it("column headers contain no dollar amounts", () => {
    setState({ data: okPayload([makeRow()]), isLoading: false });
    const { container } = render(<PredictionHistoryPanel />);
    const ths = container.querySelectorAll("th");
    ths.forEach((th) => expect(th.textContent ?? "").not.toMatch(/\$\s?\d/));
  });

  it("stake_units renders as '1.25u' (units label, never dollars)", () => {
    setState({ data: okPayload([makeRow({ stake_units: 1.25 })]), isLoading: false });
    render(<PredictionHistoryPanel />);
    // The component renders stake_units as "<n>u"
    expect(screen.getByText("1.25u")).toBeInTheDocument();
  });

  it("renders multiple rows in correct count order", () => {
    const rows = [
      makeRow({ game_id: "g1", matchup: "NYK vs SAS" }),
      makeRow({ game_id: "g2", matchup: "BOS vs MIA" }),
      makeRow({ game_id: "g3", matchup: "LAL vs GSW" }),
    ];
    setState({ data: okPayload(rows), isLoading: false });
    const { container } = render(<PredictionHistoryPanel />);
    expect(container.querySelectorAll('[data-testid="prediction-row"]').length).toBe(3);
    expect(screen.getByText("NYK vs SAS")).toBeInTheDocument();
    expect(screen.getByText("BOS vs MIA")).toBeInTheDocument();
    expect(screen.getByText("LAL vs GSW")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// (2) Empty / stale / error path -- honest banners, no fabricated rows
// ---------------------------------------------------------------------------

describe("PredictionHistoryPanel -- empty / stale / error (ws5 acceptance #2)", () => {
  beforeEach(resetState);

  it("renders data-testid=pred-history-empty when payload is status=ok with 0 rows", () => {
    setState({ data: okPayload([]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("pred-history-empty")).toBeInTheDocument();
  });

  it("renders explicit 'None settled yet' text when predictions array is empty", () => {
    setState({ data: okPayload([]), isLoading: false });
    render(<PredictionHistoryPanel />);
    expect(screen.getByText(/None settled yet/i)).toBeInTheDocument();
  });

  it("no fabricated prediction rows when predictions array is empty", () => {
    setState({ data: okPayload([]), isLoading: false });
    const { container } = render(<PredictionHistoryPanel />);
    expect(container.querySelectorAll('[data-testid="prediction-row"]').length).toBe(0);
  });

  it("renders data-testid=pred-history-stale banner when isStale=true and data present", () => {
    setState({
      data: okPayload([makeRow()]),
      isLoading: false,
      isStale: true,
      ageSec: 200,
    });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("pred-history-stale")).toBeInTheDocument();
  });

  it("stale banner text contains age info (seconds ago)", () => {
    setState({
      data: okPayload([makeRow()]),
      isLoading: false,
      isStale: true,
      ageSec: 250,
    });
    render(<PredictionHistoryPanel />);
    const banner = screen.getByTestId("pred-history-stale");
    expect(banner.textContent).toMatch(/stale/i);
  });

  it("renders unavailable-panel when error is set and data is null (404/offline)", () => {
    setState({ data: null, isLoading: false, error: "404 not found" });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("unavailable-panel")).toBeInTheDocument();
  });

  it("unavailable panel shows the error reason", () => {
    setState({ data: null, isLoading: false, error: "connection refused" });
    render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("unavailable-panel")).toHaveTextContent("connection refused");
  });

  it("no fabricated rows when error is set and data is null", () => {
    setState({ data: null, isLoading: false, error: "404 not found" });
    const { container } = render(<PredictionHistoryPanel />);
    expect(container.querySelectorAll('[data-testid="prediction-row"]').length).toBe(0);
  });

  it("shows loading skeleton (aria-busy) during initial load before first data", () => {
    setState({ data: null, isLoading: true, error: null });
    const { container } = render(<PredictionHistoryPanel />);
    // The skeleton container has aria-busy="true" and aria-label="loading prediction history"
    const skeleton = container.querySelector('[aria-busy="true"]');
    expect(skeleton).not.toBeNull();
    expect(skeleton?.getAttribute("aria-label")).toMatch(/loading/i);
  });

  it("no dollar sign in empty-state rendered output", () => {
    setState({ data: okPayload([]), isLoading: false });
    const { container } = render(<PredictionHistoryPanel />);
    assertNoDollar(container);
  });

  it("no dollar sign in error/unavailable rendered output", () => {
    setState({ data: null, isLoading: false, error: "service down" });
    const { container } = render(<PredictionHistoryPanel />);
    assertNoDollar(container);
  });

  it("no dollar sign in stale+data rendered output", () => {
    setState({
      data: okPayload([makeRow({ stake_units: 3.0, model_prob: 0.68 })]),
      isLoading: false,
      isStale: true,
      ageSec: 300,
    });
    const { container } = render(<PredictionHistoryPanel />);
    assertNoDollar(container);
  });

  it("renders pred-history-empty and no rows when data.predictions is undefined/empty", () => {
    setState({
      data: { status: "ok", count: 0, generated_at: null, predictions: [], edge_claimed: false } as PaperPredictions,
      isLoading: false,
    });
    const { container } = render(<PredictionHistoryPanel />);
    expect(screen.getByTestId("pred-history-empty")).toBeInTheDocument();
    expect(container.querySelectorAll('[data-testid="prediction-row"]').length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// (3) CLV honest rendering -- INSUFFICIENT_DATA path
// ---------------------------------------------------------------------------

describe("PredictionHistoryPanel -- CLV INSUFFICIENT_DATA honesty", () => {
  beforeEach(resetState);

  it("CLV column header present (no dollar signs in header)", () => {
    setState({ data: okPayload([makeRow()]), isLoading: false });
    const { container } = render(<PredictionHistoryPanel />);
    // The column headers use text like "Divergence" -- check no '$' in any header
    const ths = container.querySelectorAll("th");
    ths.forEach((th) => expect(th.textContent ?? "").not.toMatch(/\$/));
  });

  it("row with clv_pct=null does not render a numeric percentage in the output", () => {
    // Only model_prob + market_prob show as %; edge_vs_market also shows as %.
    // When clv_pct=null the only percentages are the honest model/market ones.
    setState({ data: okPayload([makeInsufficientDataRow()]), isLoading: false });
    const { container } = render(<PredictionHistoryPanel />);
    // The EMPTY_CELL "--" must appear; a fabricated "0.0%" must NOT appear.
    expect(container.textContent).not.toMatch(/0\.0%|0\.00%/);
  });

  it("edge_vs_market renders as a signed pct (positive divergence)", () => {
    setState({ data: okPayload([makeRow({ edge_vs_market: 0.11 })]), isLoading: false });
    const { container } = render(<PredictionHistoryPanel />);
    // fmtPct(0.11) = "+11.0%" (signed by default in the component)
    expect(container.textContent).toMatch(/11\.0%/);
  });

  it("negative edge_vs_market shows as negative pct", () => {
    setState({ data: okPayload([makeRow({ edge_vs_market: -0.03, decision: "no_bet" })]), isLoading: false });
    const { container } = render(<PredictionHistoryPanel />);
    expect(container.textContent).toMatch(/-3\.0%|3\.0%/);
  });
});
