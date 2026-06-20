import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import { PortfolioRiskPanel } from "../PortfolioRiskPanel";
import { BestBetsRisk } from "../BestBetsRisk";
import { betRiskRow, qualifyingRows } from "../riskUtils";
import type { GameEdge } from "@/lib/api";

// ---------------------------------------------------------------------------
// /risk DEEP honesty-rail tests (DISJOINT from risk.test.tsx -- this file owns
// the SELF-FETCHING panels + the no-pick / unavailable / joint<naive states):
//   * PortfolioRiskPanel: real units render, joint<naive principle, RoR
//     descriptive (never a guarantee), empty book = honest zero, unavailable
//     endpoint = honest degrade, real-money DENY banner, NO $ glyph.
//   * BestBetsRisk: a per-sport unavailable sport degrades independently and
//     NEVER fabricates a pick; when NO pick clears a floor -> honest empty
//     ("matching the efficient close is a SUCCESS"); qualifying picks render in
//     units, sorted, with NO $.
//   * riskUtils edge cases: candidates fallback, missing probs -> null (dash),
//     stake sort, no_bet never promoted.
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

// A fetch router keyed on URL substring so each sport / endpoint can be wired.
function routeFetch(map: Array<[RegExp, unknown]>, fallback: unknown) {
  return vi.fn().mockImplementation((url: string) => {
    for (const [re, body] of map) {
      if (re.test(String(url))) return Promise.resolve(jsonRes(body));
    }
    return Promise.resolve(jsonRes(fallback));
  }) as unknown as typeof fetch;
}

// ---------------------------------------------------------------------------
// PortfolioRiskPanel -- the descriptive UNIT-space portfolio view.
// ---------------------------------------------------------------------------

describe("PortfolioRiskPanel -- real units + joint<naive + RoR descriptive", () => {
  it("renders exposure/SD in units with the joint<naive principle + RoR note (no $)", async () => {
    const risk = {
      status: "ok",
      n_open: 3,
      total_exposure_units: 4.25,
      max_single_units: 2.0,
      mean_units: 1.4167,
      variance_units2: 0.25,
      ror_descriptive: true,
      ror_is_guarantee: false,
      edge_claimed: false,
      real_money_enabled: false,
      units: "probability",
    };
    global.fetch = routeFetch([[/quant\/risk/, risk]], risk);
    const { container } = render(<PortfolioRiskPanel sport="all" />);

    await waitFor(() => expect(screen.getByText("4.250u")).toBeTruthy());
    // portfolio SD = sqrt(variance) = 0.5
    expect(screen.getByText("0.500u")).toBeTruthy();
    expect(screen.getByText(/3 open/)).toBeTruthy();
    // joint < naive sum principle is stated, not a fabricated number.
    expect(screen.getByText(/joint < naive sum/i)).toBeTruthy();
    expect(screen.getByText(/correlation-adjusted joint exposure/i)).toBeTruthy();
    // RoR is descriptive, never a guarantee.
    expect(screen.getByText(/risk-of-ruin/i)).toBeTruthy();
    // real money is DENY (paper only) + bankroll in units.
    expect(screen.getByText(/real money: DENY/i)).toBeTruthy();
    expect(screen.getByText(/bankroll in units/i)).toBeTruthy();
    // NO $ glyph anywhere in the rendered portfolio panel.
    expect(container.textContent || "").not.toMatch(/\$/);
  });

  it("an EMPTY open book renders honest zero-risk, never a fabricated number", async () => {
    const risk = {
      status: "ok",
      n_open: 0,
      total_exposure_units: 0,
      max_single_units: 0,
      mean_units: 0,
      variance_units2: 0,
      ror_descriptive: true,
      ror_is_guarantee: false,
      edge_claimed: false,
      real_money_enabled: false,
    };
    global.fetch = routeFetch([[/quant\/risk/, risk]], risk);
    render(<PortfolioRiskPanel sport="all" />);
    await waitFor(() =>
      expect(screen.getByText(/nothing is at risk/i)).toBeTruthy(),
    );
    // zero-by-construction language, never a fabricated stake.
    expect(screen.getByText(/zero by construction/i)).toBeTruthy();
  });

  it("an UNAVAILABLE risk endpoint degrades honestly (HTTP error -> sentinel)", async () => {
    // getQuantRisk returns Unavailable on non-2xx; getRisk maps it to status=unavailable.
    global.fetch = vi
      .fn()
      .mockResolvedValue(jsonRes({}, 503, false)) as unknown as typeof fetch;
    render(<PortfolioRiskPanel sport="all" />);
    await waitFor(() =>
      expect(screen.getByText(/HTTP 503/)).toBeTruthy(),
    );
  });
});

// ---------------------------------------------------------------------------
// BestBetsRisk -- per-bet cards across sports, independent degrade.
// ---------------------------------------------------------------------------

const betBet = {
  market_type: "moneyline",
  side: "home",
  model_prob: 0.6,
  market_prob: 0.55,
  best_book: "bk",
  best_odds: 1.9,
  line: null,
  edge: 0.05,
  ev: 0.06,
  tier: "B",
  decision: "bet",
  stake_units: 0.9,
  flat_unit: 1.0,
  kelly_units: 0.3,
  clv_is_proxy: false,
};

const envelopeWithBet = {
  status: "ok",
  games: [
    {
      game_id: "mlb1",
      home: "HOME",
      away: "AWAY",
      status: "ok",
      best_bets: [betBet],
    },
  ],
};

describe("BestBetsRisk -- per-sport independent degrade, NEVER fabricates a pick", () => {
  it("renders ONE qualifying card in units when a pick clears the floor (no $)", async () => {
    // Wire one sport (mlb) live with a bet; all others -> unavailable sentinel.
    global.fetch = routeFetch(
      [[/bestbets\/mlb/, envelopeWithBet]],
      { status: "unavailable", reason: "offseason" },
    );
    const { container } = render(<BestBetsRisk />);
    await waitFor(() => expect(screen.getByText(/AWAY @ HOME/)).toBeTruthy());
    expect(screen.getByText(/0.90u/)).toBeTruthy(); // units staked
    expect(screen.getByText(/tier B/i)).toBeTruthy();
    expect(container.textContent || "").not.toMatch(/\$/);
    // an offseason / down sport is degraded to empty -- not a fabricated pick.
    expect(screen.getByText(/1 qualify/)).toBeTruthy();
  });

  it("when NO sport has a qualifying pick -> honest empty (efficient-close SUCCESS)", async () => {
    // Every sport returns an envelope with only a no_bet candidate.
    const noBetEnv = {
      status: "ok",
      games: [
        {
          game_id: "g",
          home: "H",
          away: "A",
          status: "ok",
          best_bets: [{ ...betBet, decision: "no_bet", tier: null, stake_units: 0 }],
        },
      ],
    };
    global.fetch = routeFetch([], noBetEnv);
    render(<BestBetsRisk />);
    await waitFor(() =>
      expect(screen.getByText(/No paper pick clears a tier floor/i)).toBeTruthy(),
    );
    expect(screen.getByText(/SUCCESS/)).toBeTruthy();
    expect(screen.getByText(/0 qualify/)).toBeTruthy();
  });

  it("every sport unavailable -> honest empty, still NEVER a fabricated bet", async () => {
    global.fetch = routeFetch([], { status: "unavailable", reason: "down" });
    render(<BestBetsRisk />);
    await waitFor(() =>
      expect(screen.getByText(/No paper pick clears a tier floor/i)).toBeTruthy(),
    );
  });
});

// ---------------------------------------------------------------------------
// riskUtils edge cases not covered by risk.test.tsx.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// QA ws2 -- risk-unit-convention-note in app/risk/page.tsx (static source check).
// The /risk honesty banner must include a sibling note (data-testid=
// "risk-unit-convention-note") explaining that per-bet units staked here are
// Kelly-style (quarter-Kelly) sized and differ from the bets board's flat
// 1.0-per-bet display unit. Verified by reading the source file directly so
// the check is immune to Server Component async rendering complexity.
// ---------------------------------------------------------------------------

describe("ws2 -- risk-unit-convention-note in app/risk/page.tsx (source check)", () => {
  it("source contains a risk-unit-convention-note element with required copy (no $)", () => {
    const { readFileSync } = require("node:fs");
    const { join, dirname } = require("node:path");
    const { fileURLToPath } = require("node:url");
    const here = dirname(fileURLToPath(import.meta.url));
    // Navigate from components/risk/__tests__/ up to webapp root, then into app/risk/.
    const src = readFileSync(
      join(here, "..", "..", "..", "app", "risk", "page.tsx"),
      "utf8",
    );
    // Must have the testid attribute.
    expect(src).toContain('data-testid="risk-unit-convention-note"');
    // Must mention Kelly-style OR quarter-Kelly.
    expect(/kelly.style|quarter.kelly/i.test(src)).toBe(true);
    // Must mention the flat 1.0-per-bet bets board convention.
    expect(/flat/i.test(src)).toBe(true);
    expect(/1\.0.{0,20}bet/i.test(src)).toBe(true);
    // Must say UNITS.
    expect(/UNITS/i.test(src)).toBe(true);
    // No bare dollar amounts anywhere in the file (a bare "NO $" rail-comment is
    // the ONLY $ in the file and is always followed by a space, never a digit).
    expect(/\$\d/.test(src)).toBe(false);
  });
});

describe("riskUtils -- deep edge cases (candidates fallback, null probs, sort)", () => {
  it("qualifyingRows reads the `candidates` array when `best_bets` is absent", () => {
    const edge = {
      game_id: "g1",
      home: "H",
      away: "A",
      status: "ok",
      candidates: [betBet],
    } as unknown as GameEdge;
    const rows = qualifyingRows([edge]);
    expect(rows.length).toBe(1);
    expect(rows[0].tier).toBe("B");
  });

  it("missing model/market prob -> null (rendered as a dash), never invented", () => {
    const edge = {
      game_id: "g2",
      home: "H",
      away: "A",
      status: "ok",
      best_bets: [
        {
          ...betBet,
          model_prob: undefined as unknown as number,
          market_prob: undefined as unknown as number,
        },
      ],
    } as unknown as GameEdge;
    const r = betRiskRow(edge, edge.best_bets![0]);
    expect(r.modelProb).toBeNull();
    expect(r.devigClose).toBeNull();
  });

  it("qualifyingRows sorts the larger stake first", () => {
    const edge = {
      game_id: "g3",
      home: "H",
      away: "A",
      status: "ok",
      best_bets: [
        { ...betBet, stake_units: 0.4 },
        { ...betBet, market_type: "total", side: "over", stake_units: 1.8 },
      ],
    } as unknown as GameEdge;
    const rows = qualifyingRows([edge]);
    expect(rows[0].stakeUnits).toBe(1.8);
    expect(rows[1].stakeUnits).toBe(0.4);
  });

  it("a no_bet candidate is dropped from qualifyingRows (never promoted)", () => {
    const edge = {
      game_id: "g4",
      home: "H",
      away: "A",
      status: "ok",
      best_bets: [{ ...betBet, decision: "no_bet" }],
    } as unknown as GameEdge;
    expect(qualifyingRows([edge]).length).toBe(0);
  });
});
