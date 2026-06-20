// records-table-w5.test.tsx -- W5-execution-browse-detail per-file tests.
//
// Per-file vitest test (NEVER run the full suite -- freezes the box).
// Run: cd /c/Users/neelj/nba-ai-system/webapp && npx vitest run "components/records/__tests__/records-table-w5" --reporter=dot
//
// Acceptance criteria (W5 workstream):
//   1. RecordsTable renders a clickable deep-link per row routing to /paper/[id].
//   2. The deep-link href encodes sport|game_id|market_type|side into the betId.
//   3. When game_id is null, NO link element is rendered (matchup still shows).
//   4. No '$' dollar-figure token appears anywhere in the table.
//   5. Link href contains the game_id substring for easy identification.
//
// HONESTY RAILS:
//   - UNITS only; no $ P&L / roi / pnl anywhere.
//   - Deep-link to /paper/ not /records/ (W5 change from W2).

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { RecordsTable } from "../RecordsTable";
import type { PaperPredictionRow } from "@/lib/types";

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

function makeRow(overrides: Partial<PaperPredictionRow> = {}): PaperPredictionRow {
  return {
    game_id:        "g-w5-001",
    matchup:        "OKC @ SAS",
    sport:          "nba",
    market_type:    "moneyline",
    side:           "home",
    model_prob:     0.61,
    market_prob:    0.53,
    edge_vs_market: 0.08,
    tier:           "A",
    stake_units:    1.0,
    decision:       "bet",
    outcome:        null,
    final_score:    null,
    clv_pct:        null,
    beat_close:     null,
    clv_is_proxy:   false,
    clv_status:     "no_close",
    line:           1.91,
    ts:             "2026-06-20T18:00:00Z",
    ...overrides,
  } as PaperPredictionRow;
}

// ---------------------------------------------------------------------------
// W5: deep-link routes to /paper/[betId]
// ---------------------------------------------------------------------------

describe("RecordsTable W5 -- deep-link to /paper/[betId]", () => {
  it("renders a clickable link for each row with a game_id", () => {
    render(<RecordsTable rows={[makeRow()]} />);
    const link = screen.getByTestId("records-row-link");
    expect(link).toBeInTheDocument();
  });

  it("link href contains /paper/ (not /records/)", () => {
    render(<RecordsTable rows={[makeRow({ game_id: "nba-2026-g1" })]} />);
    const link = screen.getByTestId("records-row-link");
    const href = link.getAttribute("href") ?? "";
    expect(href).toContain("/paper/");
    expect(href).not.toContain("/records/");
  });

  it("link href encodes the game_id as part of the betId segment", () => {
    render(<RecordsTable rows={[makeRow({ game_id: "0022300099" })]} />);
    const link = screen.getByTestId("records-row-link");
    const href = link.getAttribute("href") ?? "";
    expect(href).toContain("0022300099");
  });

  it("link href encodes sport in the betId segment", () => {
    render(<RecordsTable rows={[makeRow({ sport: "nba", game_id: "g1" })]} />);
    const link = screen.getByTestId("records-row-link");
    const href = link.getAttribute("href") ?? "";
    // The betId is URI-encoded: sport|game_id|market_type|side
    // Decoded href should contain "nba" somewhere in the betId
    expect(decodeURIComponent(href)).toContain("nba");
  });

  it("link is an anchor element with a valid href (not empty)", () => {
    render(<RecordsTable rows={[makeRow({ game_id: "g-abc" })]} />);
    const link = screen.getByTestId("records-row-link");
    const href = link.getAttribute("href") ?? "";
    expect(href.length).toBeGreaterThan("/paper/".length);
    expect(href.startsWith("/paper/")).toBe(true);
  });

  it("link wraps the matchup text and is accessible", () => {
    render(<RecordsTable rows={[makeRow({ matchup: "MIL @ CLE", game_id: "g-xyz" })]} />);
    const link = screen.getByTestId("records-row-link");
    const matchup = screen.getByTestId("records-matchup");
    // matchup element is inside the link
    expect(link.contains(matchup)).toBe(true);
    expect(matchup.textContent).toContain("MIL @ CLE");
  });
});

// ---------------------------------------------------------------------------
// W5: no link when game_id is null
// ---------------------------------------------------------------------------

describe("RecordsTable W5 -- no link when game_id is null", () => {
  it("does not render records-row-link when game_id is null", () => {
    render(<RecordsTable rows={[makeRow({ game_id: null })]} />);
    expect(screen.queryByTestId("records-row-link")).not.toBeInTheDocument();
  });

  it("still renders records-matchup as plain text when game_id is null", () => {
    render(<RecordsTable rows={[makeRow({ game_id: null, matchup: "BOS @ MIA" })]} />);
    expect(screen.queryByTestId("records-row-link")).not.toBeInTheDocument();
    const matchup = screen.getByTestId("records-matchup");
    expect(matchup.textContent).toContain("BOS @ MIA");
  });
});

// ---------------------------------------------------------------------------
// W5: multiple rows each get their own link
// ---------------------------------------------------------------------------

describe("RecordsTable W5 -- multiple rows with links", () => {
  it("renders a deep-link per row when all rows have game_id", () => {
    const rows = [
      makeRow({ game_id: "g1", matchup: "NYK @ SAS" }),
      makeRow({ game_id: "g2", matchup: "LAL @ BOS" }),
      makeRow({ game_id: "g3", matchup: "GSW @ PHX" }),
    ];
    render(<RecordsTable rows={rows} />);
    const links = screen.getAllByTestId("records-row-link");
    expect(links.length).toBe(3);
    // Each link should point to /paper/ and contain its respective game_id
    const hrefs = links.map((l) => l.getAttribute("href") ?? "");
    expect(hrefs.every((h) => h.startsWith("/paper/"))).toBe(true);
    expect(hrefs[0]).toContain("g1");
    expect(hrefs[1]).toContain("g2");
    expect(hrefs[2]).toContain("g3");
  });

  it("rows without game_id have no link; rows with game_id do", () => {
    const rows = [
      makeRow({ game_id: "g1", matchup: "A vs B" }),
      makeRow({ game_id: null, matchup: "C vs D" }),
    ];
    render(<RecordsTable rows={rows} />);
    const links = screen.getAllByTestId("records-row-link");
    expect(links.length).toBe(1);
    expect(links[0].getAttribute("href")).toContain("g1");
  });
});

// ---------------------------------------------------------------------------
// W5: honesty rail -- no $ token in table output
// ---------------------------------------------------------------------------

describe("RecordsTable W5 -- no dollar figure in DOM (honesty rail)", () => {
  it("no dollar-amount string when all W5 columns populated", () => {
    const rows = [
      makeRow({
        model_prob:   0.65,
        market_prob:  0.55,
        stake_units:  1.0,
        outcome:      "win",
        clv_pct:      0.05,
        game_id:      "g-w5-full",
      }),
    ];
    const { container } = render(<RecordsTable rows={rows} />);
    expect(/\$\s*\d/.test(container.textContent ?? "")).toBe(false);
  });

  it("no dollar-amount string when outcome is loss", () => {
    const rows = [
      makeRow({
        model_prob:   0.48,
        market_prob:  0.52,
        stake_units:  0.5,
        outcome:      "loss",
        clv_pct:      -0.02,
        game_id:      "g-loss",
      }),
    ];
    const { container } = render(<RecordsTable rows={rows} />);
    expect(/\$\s*\d/.test(container.textContent ?? "")).toBe(false);
  });

  it("no pnl or roi token in table output", () => {
    const { container } = render(<RecordsTable rows={[makeRow()]} />);
    const text = (container.textContent ?? "").toLowerCase();
    expect(text).not.toMatch(/\bpnl\b/);
    expect(text).not.toMatch(/\broi\b/);
  });

  it("units column uses 'u' suffix not a dollar sign", () => {
    render(<RecordsTable rows={[makeRow({ stake_units: 1.5 })]} />);
    const units = screen.getByTestId("records-units");
    expect(units.textContent).toBe("1.50u");
    expect(units.textContent).not.toMatch(/^\$/);
  });
});
