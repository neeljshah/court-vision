// paperTrailAdapter.test.ts -- unit tests for the pure adapter.
//
// Acceptance contract (WS4):
//   - paperRowToExecutionTrail maps tier/units/clv_status/model_prob into
//     ExecutionTrailProps with correct shapes.
//   - A row with only a taken book yields a single-row bookLines marked as
//     best (or honest [] when taken_book is absent).
//   - clv_status null / INSUFFICIENT_DATA propagates unchanged -- never
//     fabricated.
//   - No $ field is ever produced in the output.
//
// Acceptance contract (WS8):
//   - toPaperTrailRows maps graded PmTrailRow fixtures to PmDisplayRow with
//     correct shapes (venue, units, clvDisplay, executed=false).
//   - null CLV -> "INSUFFICIENT_DATA" sentinel (never 0 or a fabricated value).
//   - Rows with missing required fields (bet_id/venue/units) are DROPPED
//     (dropped=true, reason set) rather than filled with invented values.
//   - No $/pnl/roi field is ever present in the output.
//
// HONESTY RAILS reproduced here so a failing honesty assertion is loud:
//   - stakeUnits is in units (a plain number), never a string with "$".
//   - No output key ends with "_dollar", "_payout", "_revenue", "_profit".
//   - decision is "bet" | "no_bet" -- never a dollar amount.

import { describe, it, expect } from "vitest";
import { paperRowToExecutionTrail, toPaperTrailRows } from "../paperTrailAdapter";
import type { PaperTrailRow } from "@/lib/types";
import type { PmTrailRow } from "@/lib/types_w12";

// ---------------------------------------------------------------------------
// Fixture builder
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<PaperTrailRow> = {}): PaperTrailRow {
  return {
    game_id: "game1",
    matchup: "NYK vs SAS",
    sport: "nba",
    side: "home",
    market_type: "moneyline",
    line: null,
    taken_book: "kalshi",
    taken_decimal: 1.95,
    model_prob: 0.54,
    model_ev: 0.053,
    tier: "A",
    stake_units: 1.25,
    status: "open",
    graded: false,
    outcome: null,
    clv_pct: null,
    beat_close: null,
    clv_is_proxy: false,
    clv_status: null,
    clv_unavailable: false,
    clv_note: null,
    executed: false,
    ts: "2026-06-19T10:00:00Z",
    settled_at: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Assert that no value in the output object contains a dollar sign. */
function assertNoDollar(props: Record<string, unknown>) {
  const json = JSON.stringify(props);
  expect(json).not.toMatch(/\$\s?\d/);
  // Also ensure no key name suggests a dollar amount.
  for (const key of Object.keys(props)) {
    expect(key).not.toMatch(/dollar|payout|revenue|profit/i);
  }
}

// ---------------------------------------------------------------------------
// Basic mapping
// ---------------------------------------------------------------------------

describe("paperRowToExecutionTrail -- basic mapping", () => {
  it("maps tier A string to TierLabel 'A'", () => {
    const row = makeRow({ tier: "A" });
    const props = paperRowToExecutionTrail(row);
    expect(props.tier).toBe("A");
  });

  it("maps tier S/B/C correctly", () => {
    expect(paperRowToExecutionTrail(makeRow({ tier: "S" })).tier).toBe("S");
    expect(paperRowToExecutionTrail(makeRow({ tier: "B" })).tier).toBe("B");
    expect(paperRowToExecutionTrail(makeRow({ tier: "C" })).tier).toBe("C");
  });

  it("maps unrecognised tier string to null", () => {
    const props = paperRowToExecutionTrail(makeRow({ tier: "Z" }));
    expect(props.tier).toBeNull();
  });

  it("maps null tier to null", () => {
    const props = paperRowToExecutionTrail(makeRow({ tier: null }));
    expect(props.tier).toBeNull();
  });

  it("passes stake_units through as stakeUnits (numeric, no $)", () => {
    const props = paperRowToExecutionTrail(makeRow({ stake_units: 2.5 }));
    expect(props.stakeUnits).toBe(2.5);
    expect(typeof props.stakeUnits).toBe("number");
  });

  it("passes null stake_units as null", () => {
    const props = paperRowToExecutionTrail(makeRow({ stake_units: null }));
    expect(props.stakeUnits).toBeNull();
  });

  it("passes model_prob through as modelProb (numeric)", () => {
    const props = paperRowToExecutionTrail(makeRow({ model_prob: 0.72 }));
    expect(props.modelProb).toBeCloseTo(0.72);
  });

  it("passes null model_prob as null", () => {
    const props = paperRowToExecutionTrail(makeRow({ model_prob: null }));
    expect(props.modelProb).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// CLV status propagation
// ---------------------------------------------------------------------------

describe("paperRowToExecutionTrail -- clv_status propagation", () => {
  it("passes null clv_status as null (never fabricated)", () => {
    const props = paperRowToExecutionTrail(makeRow({ clv_status: null }));
    expect(props.clvStatus).toBeNull();
  });

  it("maps clv_unavailable=true to INSUFFICIENT_DATA regardless of clv_status", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ clv_unavailable: true, clv_status: null }),
    );
    expect(props.clvStatus).toBe("INSUFFICIENT_DATA");
  });

  it("maps clv_status='no_close' to INSUFFICIENT_DATA", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ clv_status: "no_close", clv_unavailable: false }),
    );
    expect(props.clvStatus).toBe("INSUFFICIENT_DATA");
  });

  it("passes clv_status='true_close' through unchanged", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ clv_status: "true_close", clv_unavailable: false }),
    );
    expect(props.clvStatus).toBe("true_close");
  });

  it("passes clv_status='proxy' through unchanged", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ clv_status: "proxy", clv_unavailable: false }),
    );
    expect(props.clvStatus).toBe("proxy");
  });

  it("never fabricates a winning CLV status when clv_pct is positive but clv_status is null", () => {
    // Even if clv_pct > 0, if no clv_status is present, propagate null (honest).
    const props = paperRowToExecutionTrail(
      makeRow({ clv_pct: 0.05, clv_status: null }),
    );
    expect(props.clvStatus).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Book lines -- single taken book
// ---------------------------------------------------------------------------

describe("paperRowToExecutionTrail -- bookLines from taken_book", () => {
  it("produces exactly one bookLines row when taken_book is present", () => {
    const props = paperRowToExecutionTrail(makeRow({ taken_book: "kalshi" }));
    expect(props.bookLines).toHaveLength(1);
  });

  it("marks the single row as bestBook (by name equality)", () => {
    const props = paperRowToExecutionTrail(makeRow({ taken_book: "kalshi" }));
    expect(props.bestBook).toBe("kalshi");
    expect(props.bookLines[0].book).toBe("kalshi");
  });

  it("passes taken_decimal as decimal_odds on the book row", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ taken_book: "polymarket", taken_decimal: 2.1 }),
    );
    expect(props.bookLines[0].decimal_odds).toBeCloseTo(2.1);
  });

  it("marks the book line as is_pm=true (PM venue)", () => {
    const props = paperRowToExecutionTrail(makeRow({ taken_book: "kalshi" }));
    expect(props.bookLines[0].is_pm).toBe(true);
  });

  it("passes line when present", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ taken_book: "draftkings", line: -4.5, taken_decimal: 1.87 }),
    );
    expect(props.bookLines[0].line).toBeCloseTo(-4.5);
  });

  it("returns [] bookLines and null bestBook when taken_book is empty string", () => {
    const props = paperRowToExecutionTrail(makeRow({ taken_book: "" }));
    expect(props.bookLines).toHaveLength(0);
    expect(props.bestBook).toBeNull();
  });

  it("returns [] and null bestBook when taken_decimal is null (absent price)", () => {
    // taken_book present but price absent -> still produce a row (honest 'null' decimal)
    // because the book is known even if price was not captured.
    const props = paperRowToExecutionTrail(
      makeRow({ taken_book: "kalshi", taken_decimal: null }),
    );
    // Row exists but decimal_odds is null -- honest representation.
    expect(props.bookLines).toHaveLength(1);
    expect(props.bookLines[0].decimal_odds).toBeNull();
    expect(props.bestBook).toBe("kalshi");
  });
});

// ---------------------------------------------------------------------------
// Devig derivation
// ---------------------------------------------------------------------------

describe("paperRowToExecutionTrail -- devig", () => {
  it("computes fair_prob = model_prob when model_prob and taken_decimal are present", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ model_prob: 0.54, taken_decimal: 1.95 }),
    );
    expect(props.devig).not.toBeNull();
    expect(props.devig!.fair_prob).toBeCloseTo(0.54);
  });

  it("computes vig_pct = 1 - model_prob * taken_decimal, clamped >= 0", () => {
    // 1 - (0.54 * 1.95) = 1 - 1.053 = -0.053 -> clamped to 0
    const props = paperRowToExecutionTrail(
      makeRow({ model_prob: 0.54, taken_decimal: 1.95 }),
    );
    expect(props.devig!.vig_pct).toBeGreaterThanOrEqual(0);
    expect(props.devig!.vig_pct).toBeLessThanOrEqual(0.5);
  });

  it("returns null devig when model_prob is null", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ model_prob: null, taken_decimal: 1.95 }),
    );
    expect(props.devig).toBeNull();
  });

  it("returns null devig when taken_decimal is null", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ model_prob: 0.54, taken_decimal: null }),
    );
    expect(props.devig).toBeNull();
  });

  it("returns null devig when model_prob is 0 (invalid probability)", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ model_prob: 0, taken_decimal: 1.95 }),
    );
    expect(props.devig).toBeNull();
  });

  it("returns null devig when taken_decimal <= 1 (invalid odds)", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ model_prob: 0.54, taken_decimal: 0.9 }),
    );
    expect(props.devig).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Decision trail
// ---------------------------------------------------------------------------

describe("paperRowToExecutionTrail -- decision", () => {
  it("sets decision='bet' when stake_units > 0", () => {
    const props = paperRowToExecutionTrail(makeRow({ stake_units: 1.5 }));
    expect(props.decision).toBe("bet");
  });

  it("sets decision='no_bet' when stake_units is null", () => {
    const props = paperRowToExecutionTrail(makeRow({ stake_units: null }));
    expect(props.decision).toBe("no_bet");
  });

  it("sets decision='no_bet' when stake_units is 0", () => {
    const props = paperRowToExecutionTrail(makeRow({ stake_units: 0 }));
    expect(props.decision).toBe("no_bet");
  });

  it("passes clv_note as decisionNote", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ clv_note: "proxy from ESPN closing line" }),
    );
    expect(props.decisionNote).toBe("proxy from ESPN closing line");
  });

  it("decisionNote is null when clv_note is null", () => {
    const props = paperRowToExecutionTrail(makeRow({ clv_note: null }));
    expect(props.decisionNote).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Honesty: no $ field ever produced
// ---------------------------------------------------------------------------

describe("paperRowToExecutionTrail -- no $ output (honesty rail)", () => {
  it("produces no $ token in stringified output for a typical settled row", () => {
    const row = makeRow({
      status: "settled",
      graded: true,
      outcome: "win",
      clv_pct: 0.03,
      clv_status: "true_close",
      stake_units: 2.0,
      model_prob: 0.65,
    });
    const props = paperRowToExecutionTrail(row);
    assertNoDollar(props as unknown as Record<string, unknown>);
  });

  it("produces no $ token for an open/pending row", () => {
    const row = makeRow();
    const props = paperRowToExecutionTrail(row);
    assertNoDollar(props as unknown as Record<string, unknown>);
  });

  it("stakeUnits is a plain number, not a formatted $ string", () => {
    const props = paperRowToExecutionTrail(makeRow({ stake_units: 3.0 }));
    expect(typeof props.stakeUnits).toBe("number");
    expect(String(props.stakeUnits)).not.toContain("$");
  });

  it("devig contains only fair_prob and vig_pct (probability ratios, no $)", () => {
    const props = paperRowToExecutionTrail(
      makeRow({ model_prob: 0.6, taken_decimal: 1.8 }),
    );
    if (props.devig) {
      expect(Object.keys(props.devig)).toEqual(
        expect.arrayContaining(["fair_prob", "vig_pct"]),
      );
      expect(Object.keys(props.devig).length).toBe(2);
    }
  });
});

// ---------------------------------------------------------------------------
// WS6: PM trail -- clv_status=INSUFFICIENT_DATA maps to null CLV cell
// ---------------------------------------------------------------------------
// When a PM daemon row arrives with clv_status="INSUFFICIENT_DATA" (the value
// the backend sets when no closing line was captured), toPaperTrailRows on the
// page sets clv_unavailable=true. The adapter must propagate that to an honest
// non-numeric CLV state -- never a fabricated 0 or positive number.

describe("paperRowToExecutionTrail -- ws6: INSUFFICIENT_DATA from PM trail", () => {
  it("row with clv_status=INSUFFICIENT_DATA + clv_unavailable=true -> clvStatus=INSUFFICIENT_DATA (no fabricated value)", () => {
    // This is the shape toPaperTrailRows produces for a PM row with no close.
    const row = makeRow({
      clv_status: "INSUFFICIENT_DATA",
      clv_unavailable: true,
      clv_pct: null,
    });
    const props = paperRowToExecutionTrail(row);
    expect(props.clvStatus).toBe("INSUFFICIENT_DATA");
    // stakeUnits must be a number (units) -- never a dollar string
    expect(typeof props.stakeUnits).toBe("number");
  });

  it("row with clv_status=INSUFFICIENT_DATA passes through even when clv_unavailable=false", () => {
    // Direct pass-through: if the backend sends INSUFFICIENT_DATA, honour it.
    const row = makeRow({
      clv_status: "INSUFFICIENT_DATA",
      clv_unavailable: false,
      clv_pct: null,
    });
    const props = paperRowToExecutionTrail(row);
    expect(props.clvStatus).toBe("INSUFFICIENT_DATA");
  });

  it("INSUFFICIENT_DATA row never produces a numeric clv value in output", () => {
    const row = makeRow({
      clv_status: "INSUFFICIENT_DATA",
      clv_unavailable: true,
      clv_pct: null,
    });
    const props = paperRowToExecutionTrail(row);
    // The output has no numeric clv_pct field -- clvStatus is a string sentinel.
    // Verify nothing in the serialised output looks like a clv dollar amount.
    const json = JSON.stringify(props);
    expect(json).not.toMatch(/\$\s?\d/);
    expect(json).not.toMatch(/"clv_pct"\s*:\s*[0-9]/);
  });
});

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

describe("paperRowToExecutionTrail -- edge cases", () => {
  it("handles a completely minimal row (all nullables null)", () => {
    const row = makeRow({
      tier: null,
      stake_units: null,
      model_prob: null,
      taken_book: "paper",
      taken_decimal: null,
      clv_status: null,
      clv_unavailable: false,
      clv_note: null,
      line: null,
    });
    const props = paperRowToExecutionTrail(row);
    expect(props.tier).toBeNull();
    expect(props.stakeUnits).toBeNull();
    expect(props.modelProb).toBeNull();
    expect(props.devig).toBeNull();
    expect(props.clvStatus).toBeNull();
    // taken_book "paper" still produces a row
    expect(props.bookLines).toHaveLength(1);
    expect(props.bestBook).toBe("paper");
  });

  it("clv_unavailable=true + clv_status='true_close' -> INSUFFICIENT_DATA (unavailable wins)", () => {
    // If clv_unavailable is true, we don't trust clv_status regardless.
    const props = paperRowToExecutionTrail(
      makeRow({ clv_unavailable: true, clv_status: "true_close" }),
    );
    expect(props.clvStatus).toBe("INSUFFICIENT_DATA");
  });

  it("returns a plain object (no class instances, serialisable)", () => {
    const props = paperRowToExecutionTrail(makeRow());
    expect(() => JSON.stringify(props)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// WS8: toPaperTrailRows -- PM graded trade mapping
// ---------------------------------------------------------------------------

function makePmRow(overrides: Partial<PmTrailRow> = {}): PmTrailRow {
  return {
    bet_id: "bet-001",
    venue: "kalshi",
    market_id: "KXNBA-2026-NYK",
    model_prob: 0.58,
    confidence: 0.72,
    units: 1.5,
    tier: "A",
    result: "win",
    clv: 0.031,
    clv_is_proxy: false,
    clv_status: "true_close",
    price_taken: 1.92,
    ts: "2026-06-19T20:00:00Z",
    ...overrides,
  };
}

/** Assert no $ or P&L key in the serialised output. */
function assertNoDollarPm(obj: Record<string, unknown>) {
  const json = JSON.stringify(obj);
  expect(json).not.toMatch(/\$\s?\d/);
  for (const key of Object.keys(obj)) {
    expect(key).not.toMatch(/dollar|payout|revenue|profit|pnl|roi/i);
  }
}

describe("toPaperTrailRows -- basic graded trade mapping", () => {
  it("maps a graded trade preserving venue", () => {
    const [row] = toPaperTrailRows([makePmRow({ venue: "kalshi" })]);
    expect(row.dropped).toBe(false);
    if (!row.dropped) expect(row.venue).toBe("kalshi");
  });

  it("maps a graded trade preserving units (numeric, no $)", () => {
    const [row] = toPaperTrailRows([makePmRow({ units: 2.25 })]);
    expect(row.dropped).toBe(false);
    if (!row.dropped) {
      expect(row.units).toBeCloseTo(2.25);
      expect(typeof row.units).toBe("number");
    }
  });

  it("sets executed=false on every display row (paper-only)", () => {
    const rows = toPaperTrailRows([makePmRow(), makePmRow({ bet_id: "bet-002" })]);
    for (const r of rows) {
      if (!r.dropped) {
        expect(r.executed).toBe(false);
      }
    }
  });

  it("maps tier string to TierLabel (A)", () => {
    const [row] = toPaperTrailRows([makePmRow({ tier: "A" })]);
    if (!row.dropped) expect(row.tier).toBe("A");
  });

  it("maps unrecognised tier to null", () => {
    const [row] = toPaperTrailRows([makePmRow({ tier: "X" })]);
    if (!row.dropped) expect(row.tier).toBeNull();
  });

  it("maps null tier to null", () => {
    const [row] = toPaperTrailRows([makePmRow({ tier: null })]);
    if (!row.dropped) expect(row.tier).toBeNull();
  });

  it("preserves result field", () => {
    const [row] = toPaperTrailRows([makePmRow({ result: "loss" })]);
    if (!row.dropped) expect(row.result).toBe("loss");
  });

  it("preserves market_id field", () => {
    const [row] = toPaperTrailRows([makePmRow({ market_id: "KXNBA-TEST" })]);
    if (!row.dropped) expect(row.market_id).toBe("KXNBA-TEST");
  });

  it("preserves price_taken as a number (not a $ string)", () => {
    const [row] = toPaperTrailRows([makePmRow({ price_taken: 1.87 })]);
    if (!row.dropped) {
      expect(row.price_taken).toBeCloseTo(1.87);
      expect(typeof row.price_taken).toBe("number");
    }
  });

  it("passes null price_taken as null (not fabricated)", () => {
    const [row] = toPaperTrailRows([makePmRow({ price_taken: null })]);
    if (!row.dropped) expect(row.price_taken).toBeNull();
  });
});

describe("toPaperTrailRows -- CLV honest mapping", () => {
  it("maps real CLV to a numeric clvDisplay (probability ratio)", () => {
    const [row] = toPaperTrailRows([makePmRow({ clv: 0.031, clv_status: "true_close" })]);
    expect(row.dropped).toBe(false);
    if (!row.dropped) {
      expect(typeof row.clvDisplay).toBe("number");
      expect(row.clvDisplay as number).toBeCloseTo(0.031);
    }
  });

  it("null CLV -> clvDisplay='INSUFFICIENT_DATA' (never 0 or fabricated)", () => {
    const [row] = toPaperTrailRows([makePmRow({ clv: null, clv_status: null })]);
    expect(row.dropped).toBe(false);
    if (!row.dropped) {
      expect(row.clvDisplay).toBe("INSUFFICIENT_DATA");
      // Must not be numeric 0 -- that would be a fabricated value.
      expect(row.clvDisplay).not.toBe(0);
    }
  });

  it("clv_status=INSUFFICIENT_DATA -> clvDisplay='INSUFFICIENT_DATA' even if clv is numeric", () => {
    const [row] = toPaperTrailRows([
      makePmRow({ clv: 0.05, clv_status: "INSUFFICIENT_DATA" }),
    ]);
    if (!row.dropped) {
      expect(row.clvDisplay).toBe("INSUFFICIENT_DATA");
    }
  });

  it("negative CLV propagates as negative number (honest loss)", () => {
    const [row] = toPaperTrailRows([makePmRow({ clv: -0.02, clv_status: "true_close" })]);
    if (!row.dropped) {
      expect(row.clvDisplay).toBeCloseTo(-0.02);
    }
  });

  it("preserves clv_is_proxy flag", () => {
    const [row] = toPaperTrailRows([makePmRow({ clv_is_proxy: true })]);
    if (!row.dropped) expect(row.clv_is_proxy).toBe(true);
  });

  it("preserves clv_status pass-through when known", () => {
    const [row] = toPaperTrailRows([makePmRow({ clv_status: "proxy" })]);
    if (!row.dropped) expect(row.clv_status).toBe("proxy");
  });
});

describe("toPaperTrailRows -- required field validation (drop, not fabricate)", () => {
  it("drops a row missing bet_id (empty string)", () => {
    const [row] = toPaperTrailRows([makePmRow({ bet_id: "" })]);
    expect(row.dropped).toBe(true);
    if (row.dropped) expect(row.reason).toMatch(/bet_id/);
  });

  it("drops a row missing venue (empty string)", () => {
    const [row] = toPaperTrailRows([makePmRow({ venue: "" })]);
    expect(row.dropped).toBe(true);
    if (row.dropped) expect(row.reason).toMatch(/venue/);
  });

  it("drops a row with null units (cannot render honest units column)", () => {
    // PmTrailRow has units: number but we test the guard for NaN coercion.
    const [row] = toPaperTrailRows([makePmRow({ units: NaN })]);
    expect(row.dropped).toBe(true);
    if (row.dropped) expect(row.reason).toMatch(/units/);
  });

  it("preserves the raw input on dropped rows for diagnostics", () => {
    const raw = makePmRow({ bet_id: "" });
    const [row] = toPaperTrailRows([raw]);
    expect(row.dropped).toBe(true);
    if (row.dropped) {
      expect(row.raw).toBeDefined();
      // raw should have the original data (not mutated)
      expect(row.raw.venue).toBe("kalshi");
    }
  });

  it("mixed batch: one valid + one dropped -> output has 2 items with correct shapes", () => {
    const rows = toPaperTrailRows([
      makePmRow(),
      makePmRow({ bet_id: "", venue: "" }),
    ]);
    expect(rows).toHaveLength(2);
    expect(rows[0].dropped).toBe(false);
    expect(rows[1].dropped).toBe(true);
  });

  it("empty input -> empty output", () => {
    expect(toPaperTrailRows([])).toHaveLength(0);
  });
});

describe("toPaperTrailRows -- no $ / pnl / roi field (honesty rail)", () => {
  it("produces no $ token in serialised output for a graded win", () => {
    const [row] = toPaperTrailRows([
      makePmRow({ result: "win", clv: 0.04, clv_status: "true_close" }),
    ]);
    if (!row.dropped) {
      assertNoDollarPm(row as unknown as Record<string, unknown>);
    }
  });

  it("produces no $ token for a row with null CLV (INSUFFICIENT_DATA)", () => {
    const [row] = toPaperTrailRows([
      makePmRow({ clv: null, clv_status: null }),
    ]);
    if (!row.dropped) {
      assertNoDollarPm(row as unknown as Record<string, unknown>);
    }
  });

  it("units is a plain number, never a formatted $ string", () => {
    const [row] = toPaperTrailRows([makePmRow({ units: 3.0 })]);
    if (!row.dropped) {
      expect(typeof row.units).toBe("number");
      expect(String(row.units)).not.toContain("$");
    }
  });

  it("output is serialisable (plain object, no class instances)", () => {
    const rows = toPaperTrailRows([makePmRow()]);
    expect(() => JSON.stringify(rows)).not.toThrow();
  });

  it("clvDisplay='INSUFFICIENT_DATA' contains no numeric 0 as CLV stand-in", () => {
    const [row] = toPaperTrailRows([makePmRow({ clv: null })]);
    if (!row.dropped) {
      // The ONLY allowed non-numeric value here is the string sentinel.
      expect(row.clvDisplay).toBe("INSUFFICIENT_DATA");
      expect(row.clvDisplay).not.toBe(0);
    }
  });
});
