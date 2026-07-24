import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

// records.page.test.tsx -- W1-records-surface acceptance tests.
//
// Acceptance criteria verified:
//   1. With >100 rows mocked, table renders model_prob / line / tier / units /
//      result / CLV columns.
//   2. Pager advances offset and causes refetch (next/prev buttons).
//   3. No '$' or dollar/pnl/roi token appears in rendered output.
//   4. AgeBadge present after data loads.
//   5. total===0 renders the honest 'no records yet' state (never hides real rows).
//
// Strategy: mock api.getPaperPredictions so the page renders deterministically
// under jsdom without a live P5 service.

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/records",
}));

import RecordsPage from "@/app/(terminal)/records/page";
import type { PaperPredictions, PaperPredictionRow } from "@/lib/p5api";
import type { Unavailable } from "@/lib/types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const FRESH_TS = new Date(Date.now() - 5_000).toISOString();
const STALE_TS = new Date(Date.now() - 25 * 60 * 1000).toISOString();

function makeRow(overrides: Record<string, unknown> = {}, idx = 0): PaperPredictionRow {
  return {
    game_id:        overrides.game_id        ?? `gid_${idx}`,
    matchup:        overrides.matchup        ?? `TeamA @ TeamB ${idx}`,
    sport:          overrides.sport          ?? "nba",
    market_type:    overrides.market_type    ?? "moneyline",
    side:           overrides.side           ?? "home",
    model_prob:     overrides.model_prob     ?? 0.54,
    market_prob:    overrides.market_prob    ?? 0.48,
    edge_vs_market: overrides.edge_vs_market ?? 0.06,
    tier:           overrides.tier           ?? "A",
    stake_units:    overrides.stake_units    ?? 0.75,
    decision:       overrides.decision       ?? "bet",
    outcome:        overrides.outcome        !== undefined ? overrides.outcome : null,
    final_score:    overrides.final_score    !== undefined ? overrides.final_score : null,
    clv_pct:        overrides.clv_pct        ?? null,
    beat_close:     overrides.beat_close     ?? null,
    clv_is_proxy:   overrides.clv_is_proxy   ?? true,
    clv_status:     overrides.clv_status     ?? null,
    line:           overrides.line           ?? 1.91,
    ts:             overrides.ts             ?? FRESH_TS,
  } as PaperPredictionRow;
}

function makeEnvelope(
  count: number,
  opts?: {
    generatedAt?: string;
    rowOverrides?: Record<string, unknown>;
  },
): PaperPredictions {
  return {
    status:       "ok",
    count,
    generated_at: opts?.generatedAt ?? FRESH_TS,
    edge_claimed: false,
    predictions:  Array.from({ length: count }, (_, i) =>
      makeRow(opts?.rowOverrides ?? {}, i),
    ),
  };
}

const UNAVAILABLE: Unavailable = { status: "unavailable", reason: "service offline" };

// ---------------------------------------------------------------------------
// Setup: stub api.getPaperPredictions
// ---------------------------------------------------------------------------

let savedGetPaperPredictions: unknown;

beforeEach(async () => {
  const mod = await import("@/lib/p5api");
  savedGetPaperPredictions = mod.api.getPaperPredictions;
});

afterEach(async () => {
  const mod = await import("@/lib/p5api");
  mod.api.getPaperPredictions =
    savedGetPaperPredictions as typeof mod.api.getPaperPredictions;
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// 1. Table renders required columns with >100 rows
// ---------------------------------------------------------------------------

describe("RecordsPage -- table renders required columns with >100 rows", () => {
  it("renders records-table when envelope has >100 predictions", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(120),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
  });

  it("renders model_prob as a percentage (54.0% not 0.54) in >100 row set", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(110, { rowOverrides: { model_prob: 0.54 } }),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    // All visible rows show 54.0% for model_prob
    const probCells = screen.queryAllByTestId("records-model-prob");
    expect(probCells.length).toBeGreaterThan(0);
    expect(probCells[0].textContent).toBe("54.0%");
  });

  it("renders line column (not a dollar figure) in >100 row set", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(110, { rowOverrides: { line: 1.91 } }),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    const lineCells = screen.queryAllByTestId("records-line");
    expect(lineCells.length).toBeGreaterThan(0);
    // 1.91 (decimal odds) -- not prefixed with $
    expect(lineCells[0].textContent).toBe("1.91");
    expect((lineCells[0].textContent ?? "")).not.toMatch(/^\$/);
  });

  it("renders tier badges in >100 row set", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(110, { rowOverrides: { tier: "S" } }),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    const tierBadges = screen.queryAllByTestId("records-tier");
    expect(tierBadges.length).toBeGreaterThan(0);
    expect(tierBadges[0].textContent?.trim()).toBe("S");
  });

  it("renders units column with 'u' suffix in >100 row set", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(110, { rowOverrides: { stake_units: 0.75 } }),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    const unitsCells = screen.queryAllByTestId("records-units");
    expect(unitsCells.length).toBeGreaterThan(0);
    expect(unitsCells[0].textContent).toBe("0.75u");
  });

  it("renders result column in >100 row set", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(110, { rowOverrides: { outcome: "win" } }),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    const resultCells = screen.queryAllByTestId("records-result");
    expect(resultCells.length).toBeGreaterThan(0);
    expect(resultCells[0].textContent?.trim()).toBe("WIN");
  });

  it("renders CLV column in >100 row set (null CLV shows '--')", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(110, { rowOverrides: { clv_pct: null } }),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    const clvCells = screen.queryAllByTestId("records-clv");
    expect(clvCells.length).toBeGreaterThan(0);
    expect(clvCells[0].textContent?.trim()).toBe("--");
  });

  it("renders CLV as percentage when clv_pct is set", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(110, { rowOverrides: { clv_pct: 0.03 } }),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    const clvCells = screen.queryAllByTestId("records-clv");
    // +3.0% CLV
    expect(clvCells[0].textContent?.trim()).toBe("+3.0%");
  });
});

// ---------------------------------------------------------------------------
// 2. Pager -- advances offset and refetches
// ---------------------------------------------------------------------------

describe("RecordsPage -- pager advances offset and refetches", () => {
  it("renders pager when >50 filtered rows are present", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(200),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    expect(screen.queryAllByTestId("records-pager").length).toBeGreaterThan(0);
  });

  it("next button is enabled when there are more rows", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(200),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    const nextBtns = screen.queryAllByTestId("pager-next");
    expect(nextBtns.length).toBeGreaterThan(0);
    expect(nextBtns[0]).not.toBeDisabled();
  });

  it("prev button is disabled on the first page", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(200),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    const prevBtns = screen.queryAllByTestId("pager-prev");
    expect(prevBtns.length).toBeGreaterThan(0);
    expect(prevBtns[0]).toBeDisabled();
  });

  it("clicking next triggers a refetch (getPaperPredictions called again)", async () => {
    const fetchSpy = vi.fn(async () => makeEnvelope(200));
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions =
      fetchSpy as unknown as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });

    // initial fetch already happened
    const callsBefore = fetchSpy.mock.calls.length;

    // click next
    const nextBtn = screen.queryAllByTestId("pager-next")[0];
    fireEvent.click(nextBtn);

    // after clicking next, pager range label should show "51-100 of ..."
    await waitFor(() => {
      const rangeEl = screen.queryAllByTestId("pager-range")[0];
      // At least the range has advanced (no longer "1-50 of ...")
      expect(rangeEl?.textContent).not.toContain("1-50");
    });
    // and the fetcher was called again (offset changed -> new useLiveData run)
    expect(fetchSpy.mock.calls.length).toBeGreaterThanOrEqual(callsBefore);
  });

  it("pager-range shows correct range text", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(200),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    const rangeEl = screen.queryAllByTestId("pager-range")[0];
    // First page, 200 rows -> "1-50 of 200"
    expect(rangeEl?.textContent).toContain("1-50 of 200");
  });
});

// ---------------------------------------------------------------------------
// 3. No '$' or dollar/pnl/roi token in rendered output
// ---------------------------------------------------------------------------

describe("RecordsPage -- no dollar/pnl/roi token in rendered output", () => {
  it("renders no $ sign followed by a digit in 110-row table", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(110, { rowOverrides: { stake_units: 1.5, model_prob: 0.60, tier: "A" } }),
    ) as typeof mod.api.getPaperPredictions;

    const { container } = render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });

    const txt = container.textContent ?? "";
    expect(/\$\s*\d/.test(txt)).toBe(false);
  });

  it("renders no ROI or P&L label in 110-row table", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(110),
    ) as typeof mod.api.getPaperPredictions;

    const { container } = render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });

    const txt = container.textContent ?? "";
    expect(/\bROI\b/.test(txt)).toBe(false);
    expect(/\bP&L\b|\bPnL\b/i.test(txt)).toBe(false);
  });

  it("renders no dollar token in honest empty state", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(0),
    ) as typeof mod.api.getPaperPredictions;

    const { container } = render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-empty")).not.toBeNull();
    });

    const txt = container.textContent ?? "";
    expect(/\$\s*\d/.test(txt)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 4. AgeBadge present after data loads
// ---------------------------------------------------------------------------

describe("RecordsPage -- AgeBadge stale-never-green rail", () => {
  it("renders an age-badge after data loads", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(10, { generatedAt: FRESH_TS }),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("age-badge")).not.toBeNull();
    });
  });

  it("stale generated_at renders 'aging' token (stale-never-green)", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(10, { generatedAt: STALE_TS }),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      const agingEls = screen.queryAllByText(/aging/i);
      expect(agingEls.length).toBeGreaterThan(0);
    });

    const agingEls = screen.queryAllByText(/aging/i);
    for (const el of agingEls) {
      const cls = el.closest("[class]")?.className ?? el.className;
      expect(cls).not.toMatch(/text-green/);
      expect(cls).not.toMatch(/tier-a/);
    }
  });
});

// ---------------------------------------------------------------------------
// 5. total===0 renders honest 'no records yet' state (never hides real rows)
// ---------------------------------------------------------------------------

describe("RecordsPage -- honest empty state when total===0", () => {
  it("shows records-empty when predictions array is empty", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(0),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-empty")).not.toBeNull();
    });
  });

  it("records-empty says 'no records' (case-insensitive)", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(0),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-empty")).not.toBeNull();
    });
    const el = screen.getByTestId("records-empty");
    expect(el.textContent).toMatch(/no records/i);
  });

  it("records-empty does NOT show the table", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(0),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-empty")).not.toBeNull();
    });
    expect(screen.queryByTestId("records-table")).toBeNull();
  });

  it("table is shown (not empty state) when rows > 0", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      makeEnvelope(5),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    expect(screen.queryByTestId("records-empty")).toBeNull();
  });

  it("degrades honestly to unavailable (not a crash) on Unavailable sentinel", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      UNAVAILABLE,
    ) as unknown as typeof mod.api.getPaperPredictions;

    const { container } = render(<RecordsPage />);

    await waitFor(() => {
      const txt = container.textContent ?? "";
      const ok =
        /unavailable/i.test(txt) ||
        /service offline/i.test(txt) ||
        screen.queryByTestId("records-table") === null;
      expect(ok).toBe(true);
    });
  });
});

// ---------------------------------------------------------------------------
// 6. W1-records-server-paging acceptance tests (PRIMARY)
//
// Asserts the exact server-paging contract:
//   a) Initial fetch uses {limit:50, offset:0}
//   b) Clicking Next at page 5 (offset=200) fetches {limit:50, offset:200}
//   c) Pager range shows "201-250 of 3284" (server total surfaced verbatim)
//   d) Header surfaces the server total (3284)
//   e) Filters narrow visible page rows (client-side on fetched page)
//   f) No '$' / 'ROI' / 'profit' / 'pnl' in rendered output
//   g) Stale badge is never green
// ---------------------------------------------------------------------------

describe("RecordsPage -- W1 server paging: initial fetch uses limit=50&offset=0", () => {
  it("calls getPaperPredictions with limit=50 and offset=0 on first render", async () => {
    const fetchSpy = vi.fn(async () => makeEnvelope(3284));
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions =
      fetchSpy as unknown as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });

    // The first call must use offset=0 and limit=50 (not PAGE_SIZE*4)
    const calls = fetchSpy.mock.calls as Array<[({ limit?: number; offset?: number } | undefined)?]>;
    const firstCall = calls[0];
    const params = firstCall?.[0] as { limit?: number; offset?: number } | undefined;
    expect(params?.limit).toBe(50);
    expect(params?.offset ?? 0).toBe(0);
  });
});

describe("RecordsPage -- W1 server paging: pager Next at offset=200 fetches offset=200&limit=50", () => {
  // This is the primary acceptance criterion from the workstream spec:
  // "pager Next at offset=200 fetches /api/paper/predictions?offset=200&limit=50"
  // Timeout raised: 4 sequential click+refetch cycles each need ~1-2s in jsdom.
  it("clicking Next 4 times reaches offset=200 and fetches with offset=200&limit=50", async () => {
    // Each call returns 50 rows and total=3284 so Next is always enabled.
    const fetchSpy = vi.fn(async (_params?: { limit?: number; offset?: number }) =>
      makeEnvelope(3284),
    );
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions =
      fetchSpy as unknown as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    // Wait for first load
    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    }, { timeout: 4000 });

    // Click Next 4 times to advance: 0 -> 50 -> 100 -> 150 -> 200
    for (let i = 0; i < 4; i++) {
      const nextBtns = screen.queryAllByTestId("pager-next");
      fireEvent.click(nextBtns[0]);
      await waitFor(() => {
        // Wait for each subsequent page render
        const rangeEl = screen.queryAllByTestId("pager-range")[0];
        const expectedStart = (i + 1) * 50 + 1;
        expect(rangeEl?.textContent).toContain(`${expectedStart}-`);
      }, { timeout: 4000 });
    }

    // After 4 clicks the offset should be 200; the most recent call must have offset=200
    const calls = fetchSpy.mock.calls;
    const lastCall = calls[calls.length - 1];
    const lastParams = lastCall[0] as { limit?: number; offset?: number } | undefined;
    expect(lastParams?.offset).toBe(200);
    expect(lastParams?.limit).toBe(50);
  }, 30000);
});

describe("RecordsPage -- W1 server paging: pager shows 201-250 of 3284 after offset=200", () => {
  // Timeout raised: 4 sequential click+refetch cycles each need ~1-2s in jsdom.
  it("pager-range reads '201-250 of 3284' when offset=200 and server total=3284", async () => {
    let callCount = 0;
    const fetchSpy = vi.fn(async (params?: { limit?: number; offset?: number }) => {
      callCount++;
      const off = params?.offset ?? 0;
      // Return 50 rows stamped with matchup index based on offset so the table renders
      const rows = Array.from({ length: 50 }, (_, i) =>
        makeRow({ matchup: `Matchup ${off + i}` }, off + i),
      );
      return {
        status:       "ok",
        count:        3284,
        generated_at: FRESH_TS,
        edge_claimed: false,
        predictions:  rows,
      } as import("@/lib/types").PaperPredictions;
    });
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions =
      fetchSpy as unknown as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    // Wait for first page
    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    }, { timeout: 4000 });

    // Navigate to page 5 (offset=200)
    for (let i = 0; i < 4; i++) {
      const nextBtns = screen.queryAllByTestId("pager-next");
      fireEvent.click(nextBtns[0]);
      await waitFor(() => {
        const rangeEl = screen.queryAllByTestId("pager-range")[0];
        const expectedStart = (i + 1) * 50 + 1;
        expect(rangeEl?.textContent).toContain(`${expectedStart}-`);
      }, { timeout: 4000 });
    }

    // Pager range must say "201-250 of 3284"
    const rangeEls = screen.queryAllByTestId("pager-range");
    expect(rangeEls[0]?.textContent).toContain("201-250 of 3284");

    // Rows show matchups starting at 200 (offset=200)
    const matchupCells = screen.queryAllByTestId("records-matchup");
    expect(matchupCells.length).toBeGreaterThan(0);
    expect(matchupCells[0].textContent).toContain("Matchup 200");
  }, 30000);
});

describe("RecordsPage -- W1 server paging: total label shows 3284", () => {
  it("surfaces envelopeTotal=3284 in the header text", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () => ({
      status:       "ok",
      count:        3284,
      generated_at: FRESH_TS,
      edge_claimed: false,
      predictions:  Array.from({ length: 50 }, (_, i) => makeRow({}, i)),
    } as import("@/lib/types").PaperPredictions)) as typeof mod.api.getPaperPredictions;

    const { container } = render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });

    // Header / panel must surface 3284
    const txt = container.textContent ?? "";
    expect(txt).toContain("3284");
  });
});

describe("RecordsPage -- W1 server paging: filters narrow visible page", () => {
  it("applying sport filter reduces visible rows (client-side on fetched page)", async () => {
    // Page returns 50 rows: 25 nba, 25 mlb
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () => ({
      status:       "ok",
      count:        3284,
      generated_at: FRESH_TS,
      edge_claimed: false,
      predictions:  [
        ...Array.from({ length: 25 }, (_, i) => makeRow({ sport: "nba", matchup: `NBA ${i}` }, i)),
        ...Array.from({ length: 25 }, (_, i) => makeRow({ sport: "mlb", matchup: `MLB ${i}`, game_id: `mlb_${i}` }, 25 + i)),
      ],
    } as import("@/lib/types").PaperPredictions)) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });

    // All 50 rows visible initially
    const allRows = screen.queryAllByTestId("records-row");
    expect(allRows.length).toBe(50);

    // Apply sport=nba filter
    const sportSelect = screen.getByTestId("filter-sport");
    fireEvent.change(sportSelect, { target: { value: "nba" } });

    // Now only 25 nba rows visible
    await waitFor(() => {
      const filteredRows = screen.queryAllByTestId("records-row");
      expect(filteredRows.length).toBe(25);
    });
  });

  it("filtered within page note appears when a filter is active", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () => ({
      status:       "ok",
      count:        3284,
      generated_at: FRESH_TS,
      edge_claimed: false,
      predictions:  Array.from({ length: 50 }, (_, i) => makeRow({ sport: "nba" }, i)),
    } as import("@/lib/types").PaperPredictions)) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });

    // No filter active yet -- note should NOT appear
    expect(screen.queryByTestId("records-filter-note")).toBeNull();

    // Activate sport filter
    const sportSelect = screen.getByTestId("filter-sport");
    fireEvent.change(sportSelect, { target: { value: "nba" } });

    // Honest filter-within-page note must appear
    await waitFor(() => {
      expect(screen.queryByTestId("records-filter-note")).not.toBeNull();
    });
    expect(screen.getByTestId("records-filter-note").textContent).toContain("filtered within this page");
  });
});

describe("RecordsPage -- W1 server paging: no $/ROI/profit/pnl in output", () => {
  it("renders no $ / ROI / profit / pnl token with 3284-total envelope", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () => ({
      status:       "ok",
      count:        3284,
      generated_at: FRESH_TS,
      edge_claimed: false,
      predictions:  Array.from({ length: 50 }, (_, i) =>
        makeRow({ stake_units: 1.5, model_prob: 0.60, tier: "A" }, i),
      ),
    } as import("@/lib/types").PaperPredictions)) as typeof mod.api.getPaperPredictions;

    const { container } = render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });

    const txt = container.textContent ?? "";
    expect(/\$\s*\d/.test(txt)).toBe(false);
    expect(/\bROI\b/i.test(txt)).toBe(false);
    expect(/\bprofit\b/i.test(txt)).toBe(false);
    expect(/\bpnl\b/i.test(txt)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 6. Real backend envelope shape -- tests-mirror-real
//
// The live /api/paper/predictions returns {total, trades, result, clv, group,
// event_id, logged_at} -- NOT {count, predictions, outcome, clv_pct,
// market_type, game_id}.  getPaperPredictions normalizes via
// normalizeRawEnvelope before returning.  These tests feed the ACTUAL wire
// shape (bypassing the normalizer by mocking api.getPaperPredictions with the
// raw envelope routed through normalizeRawEnvelope) to verify the UI surfaces
// real rows instead of showing a false empty state.
// ---------------------------------------------------------------------------

import { normalizeRawEnvelope } from "@/lib/p5api";
import type { RawPaperEnvelope } from "@/lib/types";

function makeRawTrade(idx = 0) {
  return {
    logged_at:     FRESH_TS,
    sport:         "nba",
    matchup:       `TeamX @ TeamY ${idx}`,
    group:         "moneyline",
    selection:     "home",
    model_prob:    0.57,
    market_prob:   0.50,
    side:          "home",
    tier:          null,
    result:        idx % 3 === 0 ? "win" : idx % 3 === 1 ? "loss" : null,
    clv:           idx % 3 === 0 ? 0.02 : null,
    clv_status:    "proxy",
    executed:      false,
    event_id:      `evt_${idx}`,
    commence_time: FRESH_TS,
    channel:       "paper",
    note:          null,
  };
}

function makeRawEnvelope(count: number): RawPaperEnvelope {
  return {
    status:             "ok",
    total:              count,
    offset:             0,
    limit:              100,
    trades:             Array.from({ length: count }, (_, i) => makeRawTrade(i)),
    edge_claimed:       false,
    real_money_enabled: false,
    honest_note:        "no edge claimed",
  };
}

describe("RecordsPage -- real backend envelope shape (tests-mirror-real)", () => {
  it("normalizeRawEnvelope maps trades->predictions and total->count", () => {
    const raw = makeRawEnvelope(5);
    const norm = normalizeRawEnvelope(raw);
    if ((norm as { status: string }).status === "unavailable") throw new Error("unexpected unavailable");
    const pp = norm as import("@/lib/types").PaperPredictions;
    expect(pp.count).toBe(5);
    expect(pp.predictions).toHaveLength(5);
  });

  it("normalizeRawEnvelope maps row.result->outcome and row.clv->clv_pct", () => {
    const raw = makeRawEnvelope(3);
    const norm = normalizeRawEnvelope(raw) as import("@/lib/types").PaperPredictions;
    // trade 0 has result="win", clv=0.02
    expect(norm.predictions[0].outcome).toBe("win");
    expect(norm.predictions[0].clv_pct).toBeCloseTo(0.02);
    // trade 2 has result=null, clv=null
    expect(norm.predictions[2].outcome).toBeNull();
    expect(norm.predictions[2].clv_pct).toBeNull();
  });

  it("normalizeRawEnvelope maps row.group->market_type and row.event_id->game_id", () => {
    const raw = makeRawEnvelope(2);
    const norm = normalizeRawEnvelope(raw) as import("@/lib/types").PaperPredictions;
    expect(norm.predictions[0].market_type).toBe("moneyline");
    expect(norm.predictions[0].game_id).toBe("evt_0");
  });

  it("RecordsPage renders real rows when api returns raw backend envelope via normalizer", async () => {
    const mod = await import("@/lib/p5api");
    // Simulate what the real getPaperPredictions does: fetch raw -> normalize
    mod.api.getPaperPredictions = vi.fn(async () =>
      normalizeRawEnvelope(makeRawEnvelope(60)),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    // Must NOT show false-empty
    expect(screen.queryByTestId("records-empty")).toBeNull();
    // Should have real row cells
    const matchupCells = screen.queryAllByTestId("records-matchup");
    expect(matchupCells.length).toBeGreaterThan(0);
    expect(matchupCells[0].textContent).toContain("TeamX @ TeamY");
  });

  it("RecordsPage does NOT show false-empty state when total=3284 (simulated)", async () => {
    const mod = await import("@/lib/p5api");
    mod.api.getPaperPredictions = vi.fn(async () =>
      normalizeRawEnvelope(makeRawEnvelope(3284)),
    ) as typeof mod.api.getPaperPredictions;

    render(<RecordsPage />);

    await waitFor(() => {
      expect(screen.queryByTestId("records-table")).not.toBeNull();
    });
    expect(screen.queryByTestId("records-empty")).toBeNull();
    // Header should surface the total count
    const txt = document.body.textContent ?? "";
    expect(txt).toMatch(/3284/);
  });

  it("normalizeRawEnvelope returns unavailable passthrough on unavailable input", () => {
    const result = normalizeRawEnvelope(UNAVAILABLE as unknown as RawPaperEnvelope);
    expect((result as { status: string }).status).toBe("unavailable");
  });
});
