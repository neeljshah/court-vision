import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { CoverageBars } from "../CoverageBars";
import { VerdictTrend } from "../VerdictTrend";
import { BacklogBurndown } from "../BacklogBurndown";
import { CompletenessStrip } from "../CompletenessStrip";
import { WhatsNext } from "../WhatsNext";
import type { ProgressPerSport, ProgressHistoryPoint } from "@/lib/api";

// ---------------------------------------------------------------------------
// /progress DEEP honesty-rail tests (DISJOINT from progress.test.tsx -- this
// file owns the SELF-FETCHING WhatsNext strip, the sparkline edge geometry, the
// coverage-bar clamping/composition math, the backlog 73->15 burn-down, the
// engine READY/INERT cells, and the explicit "model STATIC, NOT a live accuracy
// climb" rail). Asserts NO fabricated line + NO $.
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

// ---------------------------------------------------------------------------
// CoverageBars -- clamp + composition + the "reject counts as covered" rail.
// ---------------------------------------------------------------------------

describe("CoverageBars -- clamp, composition, REJECT-counts-as-covered rail", () => {
  it("clamps an out-of-range coverage_pct into [0,100] (never a fabricated >100% bar)", () => {
    const perSport: Record<string, ProgressPerSport> = {
      nba: {
        coverage_pct: 142, // pathological upstream value
        n_tested: 5,
        n_ship: 0,
        n_reject: 5,
        n_insufficient: 0,
        n_untested_remaining: 0,
      },
    };
    render(<CoverageBars perSport={perSport} />);
    const meter = screen.getByRole("meter");
    expect(Number(meter.getAttribute("aria-valuenow"))).toBeLessThanOrEqual(100);
    expect(meter.getAttribute("aria-valuemax")).toBe("100");
  });

  it("frames a REJECT as covered / a SUCCESS in the legend (markets efficient)", () => {
    const perSport: Record<string, ProgressPerSport> = {
      soccer: {
        coverage_pct: 40,
        n_tested: 2,
        n_ship: 0,
        n_reject: 2,
        n_insufficient: 0,
        n_untested_remaining: 3,
      },
    };
    render(<CoverageBars perSport={perSport} />);
    expect(screen.getByText(/reject\s*\(a success\)/i)).toBeTruthy();
    expect(screen.getByText(/ship/i)).toBeTruthy();
    // tested/untested are surfaced honestly.
    expect(screen.getByText(/2 tested, 3 untested/)).toBeTruthy();
  });

  it("an empty perSport object renders no bars (honest empty, not a fabricated row)", () => {
    render(<CoverageBars perSport={{}} />);
    expect(screen.getByText(/honest empty/i)).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// VerdictTrend -- sparkline geometry + the explicit not-accuracy / static rail.
// ---------------------------------------------------------------------------

describe("VerdictTrend -- sparkline geometry + model-STATIC rail", () => {
  it("a SINGLE history point still draws a centered, labelled line (no crash)", () => {
    const one: ProgressHistoryPoint[] = [
      { ts: 1, date_et: "2026-06-19", n_verdicts_cumulative: 4, backlog_total: 73, model_static: true, edge_claimed: false },
    ];
    render(<VerdictTrend history={one} />);
    const img = screen.getByRole("img");
    expect(img.getAttribute("aria-label")).toMatch(/cumulative recorded verdicts/i);
    // The model-static / not-accuracy note is always present.
    expect(screen.getByText(/STATIC until a human enables/i)).toBeTruthy();
  });

  it("explicitly labels the rise as COVERAGE, NOT a live accuracy/edge climb", () => {
    const pts: ProgressHistoryPoint[] = [
      { ts: 1, date_et: "2026-06-18", n_verdicts_cumulative: 2, backlog_total: 73, model_static: true, edge_claimed: false },
      { ts: 2, date_et: "2026-06-19", n_verdicts_cumulative: 7, backlog_total: 73, model_static: true, edge_claimed: false },
    ];
    render(<VerdictTrend history={pts} />);
    expect(screen.getByText(/NOT a live accuracy/i)).toBeTruthy();
    expect(screen.getAllByText(/7 verdicts/).length).toBeGreaterThan(0);
  });

  it("null history is an honest empty, never a fabricated line", () => {
    render(<VerdictTrend history={null} />);
    expect(screen.getByText(/honest empty/i)).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// BacklogBurndown -- the 73 -> 15 burn-down + completeness-only framing.
// ---------------------------------------------------------------------------

describe("BacklogBurndown -- 73->15 honest burn-down, completeness not edge", () => {
  it("renders 58 of 73 closed (79%) for the canonical 73->15 backlog", () => {
    render(<BacklogBurndown total={73} remaining={15} />);
    expect(screen.getByText("58")).toBeTruthy();
    expect(screen.getByText(/15 of 73 remaining/)).toBeTruthy();
    expect(screen.getByText("79%")).toBeTruthy();
    const meter = screen.getByRole("meter");
    expect(meter.getAttribute("aria-valuenow")).toBe("79");
  });

  it("frames closing items as COMPLETENESS / mostly REJECT, never an edge climb", () => {
    render(<BacklogBurndown total={73} remaining={15} />);
    expect(screen.getByText(/never fixes, ships, or flips a flag/i)).toBeTruthy();
    expect(screen.getByText(/recorded REJECT \(a\s*success\)/i)).toBeTruthy();
  });

  it("clamps a remaining > total to 0 closed (never a negative / fabricated burn-down)", () => {
    render(<BacklogBurndown total={10} remaining={20} />);
    // closed = max(0, 10-20) = 0
    expect(screen.getByText("0")).toBeTruthy();
    expect(screen.getByText("0%")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// CompletenessStrip -- engine READY-but-INERT + parity states.
// ---------------------------------------------------------------------------

describe("CompletenessStrip -- engine READY but INERT, parity states", () => {
  it("READY + engine OFF shows the INERT (OFF) cell (model never moves)", () => {
    render(<CompletenessStrip parityGreen={true} engineReady={true} engineEnabled={false} />);
    expect(screen.getByText("GREEN")).toBeTruthy();
    expect(screen.getByText("READY")).toBeTruthy();
    expect(screen.getByText("INERT (OFF)")).toBeTruthy();
    // crucially NOT "ON" -- the engine is never live here.
    expect(screen.queryByText(/^ON$/)).toBeNull();
  });

  it("an unknown parity (null) degrades to UNAVAILABLE, never a fabricated GREEN", () => {
    render(<CompletenessStrip parityGreen={null} engineReady={false} engineEnabled={false} />);
    expect(screen.getByText("UNAVAILABLE")).toBeTruthy();
    expect(screen.getByText("NOT READY")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// WhatsNext -- SELF-FETCHING top-ranked backlog strip + honest degrade.
// ---------------------------------------------------------------------------

const artifacts = {
  status: "ok",
  ledger: { rows: [], counts: {} },
  backlog: {
    note: "measurement-only",
    categories: ["UNTESTED_DATA"],
    count: 3,
    candidates: [
      { id: "c1", category: "UNTESTED_DATA", sport: "mlb", what: "test pitcher splits", priority: 90, expected_outcome: "REJECT-leaning" },
      { id: "c2", category: "UNTESTED_DATA", sport: "nba", what: "test rest deltas", priority: 40 },
      { id: "c3", category: "EXPOSE_COHERENT_MARKET", sport: "soccer", what: "expose corners total", priority: 70 },
    ],
  },
  honest_note: "calibration only",
  edge_claimed: false,
};

describe("WhatsNext -- self-fetching, ranked, honest-degrade, NO $", () => {
  it("renders the top-ranked discovered items sorted by priority (no $)", async () => {
    global.fetch = vi.fn().mockResolvedValue(jsonRes(artifacts)) as unknown as typeof fetch;
    const { container } = render(<WhatsNext />);
    await waitFor(() => expect(screen.getByText("test pitcher splits")).toBeTruthy());
    // highest priority (90) is rendered; measurement-only framing present.
    expect(screen.getByText("p90")).toBeTruthy();
    expect(screen.getByText(/measurement-only/i)).toBeTruthy();
    expect(container.textContent || "").not.toMatch(/\$/);
  });

  it("an unavailable backlog degrades to an honest empty, never a fabricated plan", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(jsonRes({}, 500, false)) as unknown as typeof fetch;
    render(<WhatsNext />);
    await waitFor(() =>
      expect(screen.getByText(/honest empty, never a fabricated plan/i)).toBeTruthy(),
    );
  });

  it("an empty candidate list renders the honest 'no next items' state", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue(
        jsonRes({ ...artifacts, backlog: { ...artifacts.backlog, candidates: [] } }),
      ) as unknown as typeof fetch;
    render(<WhatsNext />);
    await waitFor(() =>
      expect(screen.getByText(/no next items discovered/i)).toBeTruthy(),
    );
  });
});
