// games_depth_render.test.tsx -- RTL render guards for the games_depth depth
// components: CoherentPrediction, GameMarketSurface, ValidatedSignalsStrip.
//
// These complement the existing source-scan / catalog tests (games_depth.test.ts)
// by actually RENDERING each component and asserting:
//   * the ONE coherent prediction picks the highest-prob anchor side + name and
//     surfaces provenance + an uncertainty bar; missing prob -> honest "--"
//   * COHERENCE: the displayed headline prob == the model_probs value it came
//     from (fmtProb of the max model_probs entry appears in the DOM)
//   * the FULL market surface renders every market row, has NO price/$ header,
//     and renders missing devigged_prob as "--"; empty surface -> honest empty
//   * the validated-signals strip renders verdict chips per sport and an honest
//     empty line for an unknown sport
//   * NO "$"/price token in any rendered output (honesty rail)
//
// This lane writes NEW test files only and does NOT edit source/shared
// components -- shared-component bugs are REPORTED, not fixed.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { CoherentPrediction } from "../CoherentPrediction";
import { GameMarketSurface } from "../GameMarketSurface";
import { ValidatedSignalsStrip } from "../ValidatedSignalsStrip";
import type { Report } from "@/lib/api";

// --- fixtures ---------------------------------------------------------------

function report(over: Partial<Report> = {}): Report {
  return {
    status: "ok",
    sport: "nba",
    game_id: "g1",
    pregame: {
      home: "San Antonio Spurs",
      away: "New York Knicks",
      model_probs: { home_ml: 0.6123, away_ml: 0.3877 },
      leak_guard: { in_sample: false },
    },
    markets: [
      {
        market_type: "moneyline",
        side: "home",
        line: null,
        odds: 1.7,
        book: "dk",
        devigged_prob: 0.6123,
        captured_at: null,
        is_close: false,
        clv_is_proxy: true,
      },
      {
        market_type: "total",
        side: "over",
        line: 221.5,
        odds: 1.9,
        book: "dk",
        devigged_prob: 0.51,
        captured_at: null,
        is_close: false,
        clv_is_proxy: true,
      },
    ],
    ...over,
  } as Report;
}

// fmtProb mirrors MarketSurfaceTable / UncertaintyBar (one decimal percent).
const pct = (p: number) => `${(p * 100).toFixed(1)}%`;

// No rendered "$<digit>" anywhere -- the honesty rail. (Prose "$" is not used in
// these components; we assert no dollar-amount token reaches the DOM.)
function assertNoDollar(container: HTMLElement) {
  expect(container.textContent || "").not.toMatch(/\$\s*\d/);
}

// --- CoherentPrediction -----------------------------------------------------

describe("CoherentPrediction -- the one coherent pick", () => {
  it("renders the highest-prob anchor side as the team name (coherence)", () => {
    const { container } = render(
      <CoherentPrediction report={report()} sport="nba" />,
    );
    // home_ml (0.6123) > away_ml -> headline is the home team.
    expect(screen.getByText("San Antonio Spurs")).toBeInTheDocument();
    // COHERENCE: the displayed probability is exactly fmtProb(max model_probs).
    expect(screen.getByText(pct(0.6123))).toBeInTheDocument();
    assertNoDollar(container);
  });

  it("renders provenance (engine + pregame phase) and vs-close UNPROVEN", () => {
    render(<CoherentPrediction report={report()} sport="nba" />);
    // possession MC is the NBA engine label; phase is pregame.
    expect(screen.getByText(/possession MC/i)).toBeInTheDocument();
    expect(screen.getByText(/pregame/i)).toBeInTheDocument();
    expect(screen.getByText(/vs-close UNPROVEN/i)).toBeInTheDocument();
  });

  it("shows the leak-free chip when the report is leak-free", () => {
    render(<CoherentPrediction report={report()} sport="nba" />);
    expect(screen.getByText(/leak-free/i)).toBeInTheDocument();
  });

  it("uses the away team name when away is the higher-prob side", () => {
    const r = report({
      pregame: {
        home: "San Antonio Spurs",
        away: "New York Knicks",
        model_probs: { home_ml: 0.4, away_ml: 0.6 },
      },
    });
    render(<CoherentPrediction report={r} sport="nba" />);
    expect(screen.getByText("New York Knicks")).toBeInTheDocument();
    expect(screen.getByText(pct(0.6))).toBeInTheDocument();
  });

  it("degrades to an honest '--' when no model prob is present", () => {
    const r = report({ pregame: { home: "H", away: "A", model_probs: {} } });
    render(<CoherentPrediction report={r} sport="nba" />);
    // UncertaintyBar shows the EMPTY_CELL token for a missing prob.
    expect(screen.getByText("--")).toBeInTheDocument();
  });

  it("renders without crashing on a null report (no fabricated number)", () => {
    const { container } = render(
      <CoherentPrediction report={null} sport="tennis" />,
    );
    expect(screen.getByText("--")).toBeInTheDocument();
    assertNoDollar(container);
  });

  it("labels soccer with the Dixon-Coles engine provenance", () => {
    render(<CoherentPrediction report={report({ sport: "soccer" })} sport="soccer" />);
    expect(screen.getByText(/Dixon-Coles/i)).toBeInTheDocument();
  });
});

// --- GameMarketSurface ------------------------------------------------------

describe("GameMarketSurface -- full surface, NO price/$ column", () => {
  it("renders a row per market with the model probability (no price)", () => {
    const { container } = render(
      <GameMarketSurface report={report()} sport="nba" />,
    );
    // both markets rendered
    expect(screen.getByText("moneyline")).toBeInTheDocument();
    expect(screen.getByText("total")).toBeInTheDocument();
    // model probabilities (devigged) are shown, coherent with the surface
    expect(screen.getByText(pct(0.6123))).toBeInTheDocument();
    expect(screen.getByText(pct(0.51))).toBeInTheDocument();
    assertNoDollar(container);
  });

  it("has a 'model prob' header but NO price/payout/odds column header", () => {
    render(<GameMarketSurface report={report()} sport="nba" />);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent || "");
    const joined = headers.join(" ").toLowerCase();
    expect(joined).toMatch(/model prob/);
    expect(joined).not.toMatch(/price|payout|\bodds\b|\$/);
  });

  it("renders the market count in the heading", () => {
    render(<GameMarketSurface report={report()} sport="nba" />);
    expect(screen.getByText(/full market surface \(2\)/i)).toBeInTheDocument();
  });

  it("renders an honest '--' for a market with a missing devigged prob", () => {
    const r = report({
      // devigged_prob: null exercises the honest-missing path; the Report.Market
      // type declares it non-null so we cast this intentionally-degraded row.
      markets: [
        {
          market_type: "spread",
          side: "home",
          line: -3.5,
          odds: null,
          book: "dk",
          devigged_prob: null,
          captured_at: null,
          is_close: false,
          clv_is_proxy: true,
        } as unknown as NonNullable<Report["markets"]>[number],
      ],
    });
    render(<GameMarketSurface report={r} sport="nba" />);
    expect(screen.getByText("--")).toBeInTheDocument();
  });

  it("renders an honest empty state when there are no markets", () => {
    render(<GameMarketSurface report={report({ markets: [] })} sport="nba" />);
    expect(screen.getByText(/full market surface \(0\)/i)).toBeInTheDocument();
    expect(
      screen.getByText(/No market surface available/i),
    ).toBeInTheDocument();
  });

  it("renders the empty state for a null report (no fabricated surface)", () => {
    const { container } = render(
      <GameMarketSurface report={null} sport="tennis" />,
    );
    expect(screen.getByText(/No market surface available/i)).toBeInTheDocument();
    assertNoDollar(container);
  });
});

// --- ValidatedSignalsStrip --------------------------------------------------

describe("ValidatedSignalsStrip -- gate verdict chips per sport", () => {
  it("renders the soccer corners SHIP signal name + a SHIP chip", () => {
    render(<ValidatedSignalsStrip sport="soccer" />);
    expect(screen.getByText(/corners diff/i)).toBeInTheDocument();
    expect(screen.getAllByText(/SHIP/i).length).toBeGreaterThan(0);
  });

  it("renders nba signals as honest REJECTs (no fabricated edge)", () => {
    render(<ValidatedSignalsStrip sport="nba" />);
    expect(screen.getAllByText(/REJECT/i).length).toBeGreaterThan(0);
    // no SHIP chip for nba
    expect(screen.queryByText(/^SHIP$/i)).toBeNull();
  });

  it("renders tennis as honestly TIER3_BLOCKED", () => {
    render(<ValidatedSignalsStrip sport="tennis" />);
    expect(screen.getAllByText(/TIER3_BLOCKED|BLOCKED/i).length).toBeGreaterThan(
      0,
    );
  });

  it("renders an honest empty line for an unknown sport", () => {
    render(<ValidatedSignalsStrip sport="cricket" />);
    expect(
      screen.getByText(/No gate-tested signals catalogued/i),
    ).toBeInTheDocument();
  });

  it("keeps the calibration / vs-close UNPROVEN framing and no $", () => {
    const { container } = render(<ValidatedSignalsStrip sport="soccer" />);
    expect(screen.getByText(/vs-close UNPROVEN/i)).toBeInTheDocument();
    assertNoDollar(container);
  });
});
