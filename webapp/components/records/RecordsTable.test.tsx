import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

// RecordsTable.test.tsx -- unit tests for RecordsTable component.
// W2 additions: market_prob column, divergence cell, per-row deep-link.
// Verifies: columns present, units suffix, no dollar token, CLV display,
//           market_prob, divergence, per-row link href.

import { RecordsTable } from "./RecordsTable";
import type { PaperPredictionRow } from "@/lib/types";

function makeRow(overrides: Partial<PaperPredictionRow> = {}): PaperPredictionRow {
  return {
    game_id:        "g1",
    matchup:        "NYK @ SAS",
    sport:          "nba",
    market_type:    "moneyline",
    side:           "home",
    model_prob:     0.54,
    market_prob:    0.48,
    edge_vs_market: 0.06,
    tier:           "A",
    stake_units:    0.75,
    decision:       "bet",
    outcome:        null,
    final_score:    null,
    clv_pct:        null,
    beat_close:     null,
    clv_is_proxy:   true,
    clv_status:     null,
    line:           1.91,
    ts:             new Date().toISOString(),
    ...overrides,
  } as PaperPredictionRow;
}

// ---------------------------------------------------------------------------
// W1 column tests (preserved from W1-records-surface)
// ---------------------------------------------------------------------------

describe("RecordsTable -- column rendering (W1 baseline)", () => {
  it("renders records-table testid", () => {
    render(<RecordsTable rows={[makeRow()]} />);
    expect(screen.getByTestId("records-table")).toBeInTheDocument();
  });

  it("renders matchup text", () => {
    render(<RecordsTable rows={[makeRow({ matchup: "GSW @ PHX" })]} />);
    expect(screen.getByTestId("records-matchup").textContent).toContain("GSW @ PHX");
  });

  it("renders model_prob as percentage (54.0%)", () => {
    render(<RecordsTable rows={[makeRow({ model_prob: 0.54 })]} />);
    expect(screen.getByTestId("records-model-prob").textContent).toBe("54.0%");
  });

  it("renders line (1.91) -- not a $ prefix", () => {
    render(<RecordsTable rows={[makeRow({ line: 1.91 })]} />);
    const cell = screen.getByTestId("records-line");
    expect(cell.textContent).toBe("1.91");
    expect((cell.textContent ?? "")).not.toMatch(/^\$/);
  });

  it("renders tier badge for row with tier", () => {
    render(<RecordsTable rows={[makeRow({ tier: "S" })]} />);
    expect(screen.getByTestId("records-tier").textContent?.trim()).toBe("S");
  });

  it("renders units with 'u' suffix", () => {
    render(<RecordsTable rows={[makeRow({ stake_units: 0.75 })]} />);
    expect(screen.getByTestId("records-units").textContent).toBe("0.75u");
  });

  it("renders WIN result", () => {
    render(<RecordsTable rows={[makeRow({ outcome: "win" })]} />);
    expect(screen.getByTestId("records-result").textContent?.trim()).toBe("WIN");
  });

  it("renders LOSS result", () => {
    render(<RecordsTable rows={[makeRow({ outcome: "loss" })]} />);
    expect(screen.getByTestId("records-result").textContent?.trim()).toBe("LOSS");
  });

  it("renders pending when outcome is null", () => {
    render(<RecordsTable rows={[makeRow({ outcome: null })]} />);
    expect(screen.getByTestId("records-result").textContent?.trim()).toBe("pending");
  });

  it("renders '--' for null CLV", () => {
    render(<RecordsTable rows={[makeRow({ clv_pct: null })]} />);
    expect(screen.getByTestId("records-clv").textContent?.trim()).toBe("--");
  });

  it("renders '+3.0%' for clv_pct = 0.03", () => {
    render(<RecordsTable rows={[makeRow({ clv_pct: 0.03 })]} />);
    expect(screen.getByTestId("records-clv").textContent?.trim()).toBe("+3.0%");
  });

  it("renders '-2.0%' for negative CLV", () => {
    render(<RecordsTable rows={[makeRow({ clv_pct: -0.02 })]} />);
    expect(screen.getByTestId("records-clv").textContent?.trim()).toBe("-2.0%");
  });

  it("renders no $ token anywhere in the table", () => {
    const rows = [
      makeRow({ stake_units: 1.5, model_prob: 0.60, tier: "A", outcome: "win" }),
      makeRow({ stake_units: 0.5, model_prob: 0.52, tier: "B", outcome: "loss", game_id: "g2" }),
    ];
    const { container } = render(<RecordsTable rows={rows} />);
    expect(/\$\s*\d/.test(container.textContent ?? "")).toBe(false);
  });

  it("renders multiple rows (records-row testid for each)", () => {
    const rows = [makeRow(), makeRow({ game_id: "g2", matchup: "LAL @ BOS" })];
    render(<RecordsTable rows={rows} />);
    expect(screen.queryAllByTestId("records-row").length).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// W2 column tests: market_prob, divergence, per-row link
// ---------------------------------------------------------------------------

describe("RecordsTable -- W2 market_prob column", () => {
  it("renders market_prob as percentage when present", () => {
    render(<RecordsTable rows={[makeRow({ market_prob: 0.48 })]} />);
    const cell = screen.getByTestId("records-market-prob");
    expect(cell.textContent).toBe("48.0%");
  });

  it("renders '--' for null market_prob", () => {
    render(<RecordsTable rows={[makeRow({ market_prob: null })]} />);
    expect(screen.getByTestId("records-market-prob").textContent).toBe("--");
  });

  it("renders market_prob with no $ prefix", () => {
    render(<RecordsTable rows={[makeRow({ market_prob: 0.52 })]} />);
    const cell = screen.getByTestId("records-market-prob");
    expect((cell.textContent ?? "")).not.toMatch(/^\$/);
  });
});

describe("RecordsTable -- W2 divergence column", () => {
  it("renders positive divergence as +Xpp when model > market", () => {
    render(<RecordsTable rows={[makeRow({ model_prob: 0.54, market_prob: 0.48 })]} />);
    const cell = screen.getByTestId("records-divergence");
    expect(cell.textContent).toContain("+6.0pp");
  });

  it("renders negative divergence as -Xpp when model < market", () => {
    render(<RecordsTable rows={[makeRow({ model_prob: 0.44, market_prob: 0.50 })]} />);
    const cell = screen.getByTestId("records-divergence");
    expect(cell.textContent).toContain("-6.0pp");
  });

  it("renders '--' for divergence when market_prob is null", () => {
    render(<RecordsTable rows={[makeRow({ model_prob: 0.54, market_prob: null })]} />);
    expect(screen.getByTestId("records-divergence").textContent).toBe("--");
  });

  it("renders '--' for divergence when both are null", () => {
    render(<RecordsTable rows={[makeRow({ model_prob: null, market_prob: null })]} />);
    expect(screen.getByTestId("records-divergence").textContent).toBe("--");
  });
});

describe("RecordsTable -- W2/W5 per-row deep-link", () => {
  it("renders a per-row link with href to /paper/[betId] when game_id present", () => {
    render(<RecordsTable rows={[makeRow({ game_id: "nba-2026-g1" })]} />);
    const link = screen.getByTestId("records-row-link");
    expect(link).toBeInTheDocument();
    expect(link.getAttribute("href")).toContain("/paper/");
    expect(link.getAttribute("href")).toContain("nba-2026-g1");
  });

  it("does not render a link element when game_id is null", () => {
    render(<RecordsTable rows={[makeRow({ game_id: null })]} />);
    expect(screen.queryByTestId("records-row-link")).not.toBeInTheDocument();
    // matchup still renders
    expect(screen.getByTestId("records-matchup")).toBeInTheDocument();
  });
});

describe("RecordsTable -- W2 no $ token with new columns", () => {
  it("renders no $ token when all W2 columns populated", () => {
    const rows = [
      makeRow({
        model_prob: 0.60,
        market_prob: 0.52,
        stake_units: 1.0,
        outcome: "win",
        clv_pct: 0.04,
        game_id: "abc-123",
      }),
    ];
    const { container } = render(<RecordsTable rows={rows} />);
    expect(/\$\s*\d/.test(container.textContent ?? "")).toBe(false);
  });
});
