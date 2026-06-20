// HomeRecordsHero.test.tsx -- per-component vitest for W6-home-records-hero-nav.
//
// Acceptance checklist (W6 spec):
//   W6-1. Renders >=1 real prediction row from mocked /api/paper/predictions
//          payload (matchup + model_prob + tier + result cells present).
//   W6-2. Shows headline count=3284 from mocked payload (data-testid="records-hero-total").
//   W6-3. CLV strip with n_bets=0 shows INSUFFICIENT_DATA + reason; never fabricated %.
//   W6-4. Primary CTA links to /records (data-testid="cta-records").
//   W6-5. Primary CTA links to /bets (data-testid="cta-bets").
//   W6-6. NO '$', 'roi', or 'profit' substring (case-insensitive) in rendered output.
//   W6-7. Stale badge is amber/warning, never green, when isStale=true.
//   W6-8. Honest-empty block when total===0.
//   W6-9. Neutral loading state before first fetch resolves.
//   W6-10. Degrades honestly on error/unavailable -- never crashes.

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { PaperPredictions, PaperPredictionRow, ClvScoreboard } from "@/lib/types";
import type { LiveDataState } from "@/lib/useLiveData";
import * as useLiveDataMod from "@/lib/useLiveData";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRow(over: Partial<PaperPredictionRow> = {}): PaperPredictionRow {
  return {
    game_id:     "g001",
    matchup:     "LAL @ BOS",
    sport:       "nba",
    market_type: "moneyline",
    side:        "LAL",
    model_prob:  0.54,
    market_prob: 0.50,
    tier:        "A",
    outcome:     "win",
    clv_pct:     0.02,
    clv_status:  "BEAT",
    ts:          "2026-06-01T12:00:00Z",
    line:        null,
    stake_units: null,
    beat_close:  null,
    clv_is_proxy: false,
    edge_vs_market: null,
    final_score: null,
    decision:    null,
    ...over,
  };
}

function makePayload(over: Partial<PaperPredictions> = {}): PaperPredictions {
  return {
    status:      "ok",
    count:       3284,
    predictions: [makeRow()],
    edge_claimed: false,
    ...over,
  };
}

function makeClv(over: Partial<ClvScoreboard> = {}): ClvScoreboard {
  return {
    n_bets:        0,
    pct_beat_close: null,
    mean_clv_pct:  null,
    by_sport:      null,
    clv_is_proxy:  true,
    ...over,
  };
}

// Builds a LiveDataState for injecting via useLiveData spy.
// Generic: works for PaperPredictions OR ClvScoreboard.
// Default isLoading: true only when data=null AND no error override present.
function makeLiveState<T>(
  dataVal: T | null,
  over: Partial<LiveDataState<T>> = {},
): LiveDataState<T> {
  const hasError = over.error !== undefined && over.error !== null;
  return {
    data:                dataVal,
    lastUpdatedAt:       dataVal !== null ? Date.now() : null,
    ageSec:              dataVal !== null ? 5 : null,
    isStale:             false,
    error:               null,
    // isLoading: true only if no data yet AND no error (pure first-load skeleton)
    isLoading:           dataVal === null && !hasError,
    consecutiveFailures: 0,
    backoffActive:       false,
    refresh:             vi.fn(),
    ...over,
  };
}

// Import after spy declarations.
import { HomeRecordsHero } from "../HomeRecordsHero";

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Spy helper: useLiveData is called TWICE in the component (predictions + CLV).
// We mock the module-level function so both calls get deterministic states.
// First call = predictions, second call = CLV.
// ---------------------------------------------------------------------------

function spyBothCalls(
  predState: Partial<LiveDataState<PaperPredictions>> & { data: PaperPredictions | null },
  clvState: Partial<LiveDataState<ClvScoreboard>> & { data: ClvScoreboard | null },
) {
  const predFull  = makeLiveState(predState.data, predState);
  const clvFull   = makeLiveState(clvState.data,  clvState);
  let callCount = 0;
  vi.spyOn(useLiveDataMod, "useLiveData").mockImplementation(() => {
    callCount++;
    // 1st call: predictions; 2nd call: CLV
    return (callCount === 1 ? predFull : clvFull) as ReturnType<typeof useLiveDataMod.useLiveData>;
  });
}

// ---------------------------------------------------------------------------
// W6-1: renders >=1 real prediction row (matchup + model_prob + tier + result)
// ---------------------------------------------------------------------------

describe("HomeRecordsHero -- W6-1 renders real prediction rows", () => {
  it("renders at least one matchup cell from mocked predictions", () => {
    spyBothCalls(
      { data: makePayload() },
      { data: makeClv() },
    );
    render(<HomeRecordsHero />);
    const matchupCells = screen.getAllByTestId("row-matchup");
    expect(matchupCells.length).toBeGreaterThanOrEqual(1);
    expect(matchupCells[0].textContent).toContain("LAL @ BOS");
  });

  it("renders model_prob cell with correct percentage", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv() });
    render(<HomeRecordsHero />);
    const probCells = screen.getAllByTestId("row-model-prob");
    expect(probCells.length).toBeGreaterThanOrEqual(1);
    // 0.54 -> "54.0%"
    expect(probCells[0].textContent).toMatch(/54/);
  });

  it("renders tier cell", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv() });
    render(<HomeRecordsHero />);
    const tierCells = screen.getAllByTestId("row-tier");
    expect(tierCells.length).toBeGreaterThanOrEqual(1);
    expect(tierCells[0].textContent).toBe("A");
  });

  it("renders outcome/result cell", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv() });
    render(<HomeRecordsHero />);
    const outcomeCells = screen.getAllByTestId("row-outcome");
    expect(outcomeCells.length).toBeGreaterThanOrEqual(1);
    expect(outcomeCells[0].textContent).toMatch(/win/i);
  });

  it("renders the preview table when rows exist", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv() });
    render(<HomeRecordsHero />);
    expect(screen.getByTestId("records-hero-table")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// W6-2: shows headline total count=3284
// ---------------------------------------------------------------------------

describe("HomeRecordsHero -- W6-2 shows headline total count", () => {
  it("shows total count=3284 from mocked payload", () => {
    spyBothCalls(
      { data: makePayload({ count: 3284 }) },
      { data: makeClv() },
    );
    render(<HomeRecordsHero />);
    const totalEl = screen.getByTestId("records-hero-total");
    expect(totalEl.textContent).toMatch(/3[,.]?284|3284/);
  });

  it("shows updated total count when count changes", () => {
    spyBothCalls(
      { data: makePayload({ count: 100 }) },
      { data: makeClv() },
    );
    render(<HomeRecordsHero />);
    const totalEl = screen.getByTestId("records-hero-total");
    expect(totalEl.textContent).toContain("100");
  });
});

// ---------------------------------------------------------------------------
// W6-3: CLV strip -- n_bets=0 shows INSUFFICIENT_DATA + reason; no fabricated %
// ---------------------------------------------------------------------------

describe("HomeRecordsHero -- W6-3 CLV strip INSUFFICIENT_DATA when n_bets=0", () => {
  it("renders the CLV strip element", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv({ n_bets: 0 }) });
    render(<HomeRecordsHero />);
    expect(screen.getByTestId("clv-strip")).toBeTruthy();
  });

  it("shows INSUFFICIENT_DATA when n_bets=0", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv({ n_bets: 0 }) });
    render(<HomeRecordsHero />);
    const el = screen.getByTestId("clv-insufficient");
    expect(el.textContent).toContain("INSUFFICIENT_DATA");
  });

  it("CLV strip INSUFFICIENT_DATA includes an explanatory reason", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv({ n_bets: 0 }) });
    render(<HomeRecordsHero />);
    const el = screen.getByTestId("clv-insufficient");
    // Must give a reason -- not just the label
    expect((el.textContent ?? "").length).toBeGreaterThan("INSUFFICIENT_DATA".length);
  });

  it("CLV strip INSUFFICIENT_DATA does NOT contain a fabricated % figure", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv({ n_bets: 0 }) });
    render(<HomeRecordsHero />);
    const el = screen.getByTestId("clv-insufficient");
    // Must not have something like "54.2%" or "12.3%"
    expect(el.textContent).not.toMatch(/\d+\.\d+%/);
  });

  it("CLV strip shows n= count when n_bets > 0", () => {
    spyBothCalls(
      { data: makePayload() },
      { data: makeClv({ n_bets: 42, pct_beat_close: 0.6, clv_is_proxy: false }) },
    );
    render(<HomeRecordsHero />);
    const el = screen.getByTestId("clv-value");
    expect(el.textContent).toContain("42");
  });

  it("CLV strip shows pct_beat_close % when n_bets > 0 and value is available", () => {
    spyBothCalls(
      { data: makePayload() },
      { data: makeClv({ n_bets: 42, pct_beat_close: 0.619, clv_is_proxy: false }) },
    );
    render(<HomeRecordsHero />);
    const el = screen.getByTestId("clv-value");
    // 0.619 -> "61.9%"
    expect(el.textContent).toContain("61.9%");
  });

  it("CLV strip shows 'insufficient' state when CLV data unavailable (null)", () => {
    spyBothCalls(
      { data: makePayload() },
      // Simulate CLV data still loading (null)
      { data: null as unknown as ClvScoreboard },
    );
    render(<HomeRecordsHero />);
    // Strip renders in loading mode, not crashed
    expect(screen.getByTestId("clv-strip")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// W6-4 & W6-5: primary CTA links to /records and /bets
// ---------------------------------------------------------------------------

describe("HomeRecordsHero -- W6-4/W6-5 primary CTAs /records and /bets", () => {
  it("has a link to /records (data-testid=cta-records)", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv() });
    render(<HomeRecordsHero />);
    const link = screen.getByTestId("cta-records");
    expect(link).toBeTruthy();
    expect(link.getAttribute("href")).toBe("/records");
  });

  it("has a link to /bets (data-testid=cta-bets)", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv() });
    render(<HomeRecordsHero />);
    const link = screen.getByTestId("cta-bets");
    expect(link).toBeTruthy();
    expect(link.getAttribute("href")).toBe("/bets");
  });

  it("CTAs still render when count=0 (honest-empty state)", () => {
    spyBothCalls(
      { data: makePayload({ count: 0, predictions: [] }) },
      { data: makeClv() },
    );
    render(<HomeRecordsHero />);
    expect(screen.getByTestId("cta-records")).toBeTruthy();
    expect(screen.getByTestId("cta-bets")).toBeTruthy();
  });

  it("CTA links have focus-visible ring classes", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv() });
    render(<HomeRecordsHero />);
    const recordsLink = screen.getByTestId("cta-records");
    expect(recordsLink.className).toMatch(/focus-visible:ring-2/);
    const betsLink = screen.getByTestId("cta-bets");
    expect(betsLink.className).toMatch(/focus-visible:ring-2/);
  });
});

// ---------------------------------------------------------------------------
// W6-6: NO '$', 'roi', or 'profit' substring in rendered output
// ---------------------------------------------------------------------------

describe("HomeRecordsHero -- W6-6 no $ / roi / profit in rendered output", () => {
  it("no $ in happy path (rows present)", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv() });
    const { container } = render(<HomeRecordsHero />);
    expect(container.textContent ?? "").not.toMatch(/\$/);
  });

  it("no 'roi' in happy path (case-insensitive)", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv() });
    const { container } = render(<HomeRecordsHero />);
    expect((container.textContent ?? "").toLowerCase()).not.toMatch(/\broi\b/);
  });

  it("no 'profit' in happy path (case-insensitive)", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv() });
    const { container } = render(<HomeRecordsHero />);
    expect((container.textContent ?? "").toLowerCase()).not.toMatch(/\bprofit\b/);
  });

  it("no $ when total=0 (honest-empty state)", () => {
    spyBothCalls(
      { data: makePayload({ count: 0, predictions: [] }) },
      { data: makeClv() },
    );
    const { container } = render(<HomeRecordsHero />);
    expect(container.textContent ?? "").not.toMatch(/\$/);
  });

  it("no $ during loading state", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState(null, { isLoading: true, ageSec: null, lastUpdatedAt: null }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    const { container } = render(<HomeRecordsHero />);
    expect(container.textContent ?? "").not.toMatch(/\$/);
  });

  it("no $ in unavailable/error state", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState(null, { error: "endpoint failed" }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    const { container } = render(<HomeRecordsHero />);
    expect(container.textContent ?? "").not.toMatch(/\$/);
  });

  it("no roi or profit in CLV insufficient state", () => {
    spyBothCalls(
      { data: makePayload() },
      { data: makeClv({ n_bets: 0 }) },
    );
    const { container } = render(<HomeRecordsHero />);
    const txt = (container.textContent ?? "").toLowerCase();
    expect(txt).not.toMatch(/\broi\b/);
    expect(txt).not.toMatch(/\bprofit\b/);
  });
});

// ---------------------------------------------------------------------------
// W6-7: stale badge is amber/warning, never green
// ---------------------------------------------------------------------------

describe("HomeRecordsHero -- W6-7 stale badge is amber, never green", () => {
  it("shows stale badge when isStale=true", () => {
    spyBothCalls(
      { data: makePayload(), isStale: true, ageSec: 120 },
      { data: makeClv() },
    );
    render(<HomeRecordsHero />);
    expect(screen.getByTestId("records-hero-stale-badge")).toBeTruthy();
  });

  it("stale badge text contains 'stale'", () => {
    spyBothCalls(
      { data: makePayload(), isStale: true, ageSec: 180 },
      { data: makeClv() },
    );
    render(<HomeRecordsHero />);
    const badge = screen.getByTestId("records-hero-stale-badge");
    expect((badge.textContent ?? "").toLowerCase()).toContain("stale");
  });

  it("stale badge uses amber/warning class, NOT red/danger or green/success", () => {
    spyBothCalls(
      { data: makePayload(), isStale: true, ageSec: 120 },
      { data: makeClv() },
    );
    const { container } = render(<HomeRecordsHero />);
    const badge = container.querySelector("[data-testid='records-hero-stale-badge']");
    expect(badge).toBeTruthy();
    const cls = badge?.className ?? "";
    expect(cls).not.toMatch(/bg-danger|text-danger|bg-red|text-red/);
    expect(cls).not.toMatch(/bg-success|text-success|bg-green|text-green/);
    // Must use amber/warning
    expect(cls).toMatch(/warning|amber/);
  });

  it("no stale badge when isStale=false", () => {
    spyBothCalls(
      { data: makePayload(), isStale: false },
      { data: makeClv() },
    );
    render(<HomeRecordsHero />);
    expect(screen.queryByTestId("records-hero-stale-badge")).toBeNull();
  });

  it("no bg-success (green) in initial loading state", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState(null, { isLoading: true, ageSec: null, lastUpdatedAt: null }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    const { container } = render(<HomeRecordsHero />);
    expect(container.innerHTML).not.toContain("bg-success");
  });
});

// ---------------------------------------------------------------------------
// W6-8: honest-empty block when total===0
// ---------------------------------------------------------------------------

describe("HomeRecordsHero -- W6-8 honest-empty when total=0", () => {
  it("renders honest-empty block when count=0", () => {
    spyBothCalls(
      { data: makePayload({ count: 0, predictions: [] }) },
      { data: makeClv() },
    );
    render(<HomeRecordsHero />);
    expect(screen.getByTestId("records-hero-empty")).toBeTruthy();
  });

  it("empty state contains explanatory text (never blank)", () => {
    spyBothCalls(
      { data: makePayload({ count: 0, predictions: [] }) },
      { data: makeClv() },
    );
    render(<HomeRecordsHero />);
    const emptyBlock = screen.getByTestId("records-hero-empty");
    expect((emptyBlock.textContent ?? "").length).toBeGreaterThan(10);
  });

  it("no preview table when count=0", () => {
    spyBothCalls(
      { data: makePayload({ count: 0, predictions: [] }) },
      { data: makeClv() },
    );
    render(<HomeRecordsHero />);
    expect(screen.queryByTestId("records-hero-table")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// W6-9: neutral loading state before first fetch
// ---------------------------------------------------------------------------

describe("HomeRecordsHero -- W6-9 neutral loading state", () => {
  it("shows loading skeleton when isLoading=true and data=null", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState(null, { isLoading: true, ageSec: null, lastUpdatedAt: null }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    render(<HomeRecordsHero />);
    expect(screen.getByTestId("records-hero-loading")).toBeTruthy();
  });

  it("loading state contains 'loading' or 'checking' text", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState(null, { isLoading: true, ageSec: null, lastUpdatedAt: null }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    render(<HomeRecordsHero />);
    const loadingEl = screen.getByTestId("records-hero-loading");
    expect((loadingEl.textContent ?? "").toLowerCase()).toMatch(/load|check/);
  });

  it("does not show the total count during loading", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState(null, { isLoading: true, ageSec: null, lastUpdatedAt: null }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    render(<HomeRecordsHero />);
    expect(screen.queryByTestId("records-hero-total")).toBeNull();
  });

  it("renders without crashing (baseline smoke)", () => {
    spyBothCalls({ data: makePayload() }, { data: makeClv() });
    expect(() => render(<HomeRecordsHero />)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// W6-10: honest unavailable / error state
// ---------------------------------------------------------------------------

describe("HomeRecordsHero -- W6-10 unavailable / error state", () => {
  it("shows unavailable message when data=null and error is set", () => {
    // isLoading must be false for error state to render (first load already failed)
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState(null, { error: "both endpoints failed", isLoading: false }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    render(<HomeRecordsHero />);
    expect(screen.getByTestId("records-hero-unavailable")).toBeTruthy();
  });

  it("unavailable state carries explanatory text", () => {
    vi.spyOn(useLiveDataMod, "useLiveData").mockReturnValue(
      makeLiveState(null, { error: "endpoint timeout", isLoading: false }) as ReturnType<typeof useLiveDataMod.useLiveData>,
    );
    render(<HomeRecordsHero />);
    const el = screen.getByTestId("records-hero-unavailable");
    expect((el.textContent ?? "").length).toBeGreaterThan(10);
  });
});
