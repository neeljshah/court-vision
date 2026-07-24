import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { BestBetRiskCard } from "../BestBetRiskCard";
import { ExposureLimitsPanel } from "../ExposureLimitsPanel";
import { PortfolioRiskPanel } from "../PortfolioRiskPanel";
import { RISK_TERMS } from "../riskTerms";
import {
  betRiskRow,
  qualifyingRows,
  pctOrDash,
  unitsOrDash,
  TIER_FLOORS,
  PROXY_FLOOR_BUMP,
} from "../riskUtils";
import type { GameEdge } from "@/lib/api";

// ---------------------------------------------------------------------------
// /risk RISK-page honesty-rail tests:
//   * riskUtils builds per-bet + qualifying rows correctly (units only, no $)
//   * a no_bet candidate is never promoted to a fabricated tier/stake
//   * RISK_TERMS never imply a $ edge and are descriptive (no money/profit promise)
//   * tier-floor policy mirrors exec_decision (A 0.08 / B 0.04 / C 0.02, +0.01 proxy)
//   * BestBetRiskCard + ExposureLimitsPanel render without a $ glyph
//   * NO risk source file emits a $/pnl/roi/payout/bankroll-money field
// ---------------------------------------------------------------------------

const edge: GameEdge = {
  game_id: "g1",
  home: "HOME",
  away: "AWAY",
  status: "ok",
  best_bets: [
    {
      market_type: "moneyline",
      side: "home",
      model_prob: 0.62,
      market_prob: 0.55,
      best_book: "bk",
      best_odds: 1.9,
      line: null,
      edge: 0.07,
      ev: 0.09,
      tier: "A",
      decision: "bet",
      stake_units: 1.4,
      flat_unit: 1.0,
      kelly_units: 0.4,
      clv_is_proxy: false,
    },
    {
      market_type: "total",
      side: "over",
      model_prob: 0.5,
      market_prob: 0.5,
      best_book: "bk",
      best_odds: 1.9,
      line: 7.5,
      edge: 0.0,
      ev: 0.0,
      tier: null,
      decision: "no_bet",
      stake_units: 0,
      flat_unit: 0,
      kelly_units: 0,
      clv_is_proxy: false,
      reason: "EV below the C floor (no bet)",
    },
  ],
};

describe("riskUtils -- honest unit-space rows", () => {
  it("builds a per-bet row with units + model-vs-close (no $)", () => {
    const r = betRiskRow(edge, edge.best_bets![0]);
    expect(r.matchup).toBe("AWAY @ HOME");
    expect(r.market).toBe("moneyline home");
    expect(r.tier).toBe("A");
    expect(r.decision).toBe("bet");
    expect(r.stakeUnits).toBe(1.4);
    expect(r.kellyUnits).toBe(0.4);
    expect(r.modelProb).toBe(0.62);
    expect(r.devigClose).toBe(0.55);
  });

  it("never promotes a no_bet to a fabricated tier/stake", () => {
    const r = betRiskRow(edge, edge.best_bets![1]);
    expect(r.decision).toBe("no_bet");
    expect(r.tier).toBeNull();
    expect(r.stakeUnits).toBeNull();
    expect(r.reason).toMatch(/no bet/i);
  });

  it("qualifyingRows keeps only decision='bet'", () => {
    const rows = qualifyingRows([edge]);
    expect(rows.length).toBe(1);
    expect(rows[0].tier).toBe("A");
  });

  it("formatters give an honest dash on missing values", () => {
    expect(pctOrDash(null)).toBe("--");
    expect(pctOrDash(0.5)).toBe("50.0%");
    expect(unitsOrDash(null)).toBe("--");
    expect(unitsOrDash(1.5)).toBe("1.50u");
  });

  it("tier floors mirror exec_decision (A 0.08 / B 0.04 / C 0.02, +0.01 proxy)", () => {
    expect(TIER_FLOORS.map((t) => [t.tier, t.floor])).toEqual([
      ["A", 0.08],
      ["B", 0.04],
      ["C", 0.02],
    ]);
    expect(PROXY_FLOOR_BUMP).toBe(0.01);
  });
});

describe("RISK_TERMS -- descriptive, never a $ edge", () => {
  it("defines the core risk vocabulary", () => {
    for (const k of ["kelly", "quarter_kelly", "ror", "floor", "exposure", "joint"]) {
      expect(RISK_TERMS[k], `missing risk term: ${k}`).toBeTruthy();
      expect(RISK_TERMS[k].length).toBeGreaterThan(20);
    }
  });

  it("RoR is framed as descriptive, never a guarantee", () => {
    expect(RISK_TERMS.ror).toMatch(/never|not/i);
    expect(RISK_TERMS.ror).toMatch(/guarantee/i);
  });

  it("never implies a dollar amount or profit edge", () => {
    const blob = Object.values(RISK_TERMS).join(" ");
    expect(/\$\d/.test(blob)).toBe(false);
    expect(blob).toMatch(/UNITS|units/);
  });
});

describe("risk components render without a $ glyph", () => {
  it("BestBetRiskCard shows units + tier, no $", () => {
    const r = betRiskRow(edge, edge.best_bets![0]);
    const { container } = render(
      <ul>
        <BestBetRiskCard row={r} />
      </ul>,
    );
    expect(screen.getByText(/AWAY @ HOME/)).toBeTruthy();
    expect(container.textContent || "").not.toMatch(/\$/);
  });

  it("ExposureLimitsPanel shows the tier-floor policy, no $", () => {
    const { container } = render(<ExposureLimitsPanel />);
    expect(screen.getByText(/tier EV-floor policy/i)).toBeTruthy();
    expect(container.textContent || "").not.toMatch(/\$/);
  });
});

describe("NO $ field anywhere in the risk source", () => {
  it("no risk source file emits a money field", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const root = join(dir, "..");
    const files = readdirSync(root).filter(
      (f) => f.endsWith(".ts") || f.endsWith(".tsx"),
    );
    expect(files.length).toBeGreaterThan(0);
    // Ban any real money-VALUE token: a $-amount, a quoted-$ literal, pnl/roi/
    // payout/dollar fields. A bare "NO $" rail-statement is the ONLY $ allowed and
    // never carries a digit -- so /\$\d/ + the word bans cover every dishonest case.
    const banned = /\$\d|["']\$["']|\bpnl\b|\broi\b|payout|\bdollars?\b/i;
    for (const f of files) {
      const src = readFileSync(join(root, f), "utf8");
      expect(banned.test(src), `banned money token in ${f}`).toBe(false);
    }
  });
});

// ---------------------------------------------------------------------------
// QA #3 / iter10-P2: unit-convention clarity
//   * PortfolioRiskPanel renders an InfoTip / note mentioning Kelly-style sizing
//     vs the flat 1.0-per-bet board convention.
//   * Both texts say "UNITS" and never contain "$".
//   * A static note extracted from paper/page.tsx also says UNITS, no "$".
// ---------------------------------------------------------------------------

const realFetch = global.fetch;
afterEach(() => {
  global.fetch = realFetch;
  vi.restoreAllMocks();
});

// Minimal /api/quant/risk response for the convention-note render test.
const RISK_OPEN = {
  status: "ok",
  n_open: 2,
  total_exposure_units: 2.1,
  max_single_units: 1.5,
  mean_units: 1.05,
  variance_units2: 0.18,
  real_money_enabled: false,
};

describe("QA #3 / iter10-P2 -- unit-convention clarity in PortfolioRiskPanel", () => {
  it("renders the unit-convention note mentioning Kelly-style sizing (no $)", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => RISK_OPEN,
      }) as unknown as typeof fetch;

    const { container } = render(<PortfolioRiskPanel sport="all" />);

    // Wait for the data to load so the convention note appears.
    await waitFor(() =>
      expect(screen.getByTestId("unit-convention-note")).toBeTruthy(),
    );

    const note = screen.getByTestId("unit-convention-note");
    const text = note.textContent ?? "";

    // Must mention Kelly-style sizing.
    expect(text).toMatch(/kelly/i);
    // Must mention the flat 1.0-per-bet board convention.
    expect(text).toMatch(/flat/i);
    expect(text).toMatch(/1\.0.{0,10}bet/i);
    // Must say UNITS.
    expect(text).toMatch(/units/i);
    // Must NOT contain a dollar sign.
    expect(text).not.toMatch(/\$/);
    // The whole panel output must also be dollar-free.
    expect(container.textContent || "").not.toMatch(/\$/);
  });

  it("InfoTip is present in the convention note and its aria-label is descriptive", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => RISK_OPEN,
      }) as unknown as typeof fetch;

    render(<PortfolioRiskPanel sport="all" />);

    await waitFor(() =>
      expect(screen.getByTestId("unit-convention-note")).toBeTruthy(),
    );

    // The InfoTip inside the convention note should be findable by its aria-label.
    const trigger = screen.getByLabelText(/unit convention/i);
    expect(trigger).toBeTruthy();
  });
});

describe("QA #3 / iter10-P2 -- unit-convention note text on /paper (static)", () => {
  it("paper-unit-convention-note static copy mentions Kelly-style, flat 1.0-per-bet, UNITS, no $", async () => {
    // Render the real PaperPage so the test fails if the copy in page.tsx regresses.
    // The note (data-testid="paper-unit-convention-note") is in the static header and
    // always present regardless of fetch state -- but we mock fetch so the effect does
    // not produce unhandled promise rejections.
    global.fetch = vi
      .fn()
      .mockResolvedValue({
        ok: false,
        status: 503,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ status: "unavailable", reason: "test" }),
      }) as unknown as typeof fetch;

    const { default: PaperPage } = await import("@/app/(terminal)/paper/page");
    render(<PaperPage />);

    const note = screen.getByTestId("paper-unit-convention-note");
    const text = note.textContent ?? "";

    expect(text).toMatch(/kelly/i);
    expect(text).toMatch(/flat/i);
    expect(text).toMatch(/1\.0.{0,10}bet/i);
    expect(text).toMatch(/units/i);
    expect(text).not.toMatch(/\$/);
    // Confirm no curly/smart apostrophe (U+2019) leaked into the rendered text.
    expect(text.includes("’")).toBe(false);
  });
});
