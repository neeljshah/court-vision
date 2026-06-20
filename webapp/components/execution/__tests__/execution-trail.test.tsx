// ExecutionTrail -- WS5 component tests.
//
// Per-file vitest test (NEVER run the full suite -- freezes the box).
// Run: cd /c/Users/neelj/nba-ai-system/webapp && npx vitest run components/execution/__tests__/execution-trail.test.tsx
//
// Covers:
//   * Renders multiple book lines in the shopping table.
//   * Best line is highlighted (emerald badge + row testid).
//   * Devig section shows fair_prob and vig_pct as percentages (no $).
//   * Decision trail shows no_bet / units / tier correctly.
//   * Real-money DENY note is always visible.
//   * No $ appears anywhere in rendered output.
//   * Empty bookLines -> honest unavailable state, still renders decision trail.
//   * loading=true -> checking... text shown.
//   * error prop -> Unavailable + DENY note, no crash.
//   * CLV INSUFFICIENT_DATA shown honestly.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { ExecutionTrail } from "../ExecutionTrail";
import type { ExecutionTrailProps, BookLineRow, DevigResult } from "../ExecutionTrail";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const BOOK_LINES: BookLineRow[] = [
  { book: "DraftKings", decimal_odds: 1.91, line: null, is_pm: false, captured_at: null },
  { book: "FanDuel", decimal_odds: 1.93, line: null, is_pm: false, captured_at: null },
  { book: "Kalshi", decimal_odds: 1.96, line: null, is_pm: true, captured_at: null },
];

const DEVIG: DevigResult = {
  fair_prob: 0.518,
  vig_pct: 0.045,
};

function makeProps(overrides: Partial<ExecutionTrailProps> = {}): ExecutionTrailProps {
  return {
    bookLines: BOOK_LINES,
    bestBook: "Kalshi",
    devig: DEVIG,
    decision: "bet",
    stakeUnits: 1.25,
    tier: "A",
    clvStatus: "INSUFFICIENT_DATA",
    modelProb: 0.54,
    decisionNote: null,
    loading: false,
    error: null,
    ...overrides,
  };
}

// Shared no-$ assertion.
function noDollar(container: HTMLElement) {
  const text = container.textContent ?? "";
  // A real $ amount ($ next to a digit) is banned. Prose "no $" is the rail.
  expect(/\$\s*\d|\d\s*\$/.test(text), "no $ amount in rendered output").toBe(false);
}

// ---------------------------------------------------------------------------
// Book lines table
// ---------------------------------------------------------------------------

describe("ExecutionTrail -- book lines table", () => {
  it("renders all book names in the table", () => {
    render(<ExecutionTrail {...makeProps()} />);
    expect(screen.getByText("DraftKings")).toBeTruthy();
    expect(screen.getByText("FanDuel")).toBeTruthy();
    expect(screen.getByText("Kalshi")).toBeTruthy();
  });

  it("renders decimal odds for each book (no $ column header)", () => {
    render(<ExecutionTrail {...makeProps()} />);
    // Decimal odds for each book must appear as formatted text.
    expect(screen.getByText("1.91")).toBeTruthy();
    expect(screen.getByText("1.93")).toBeTruthy();
    expect(screen.getByText("1.96")).toBeTruthy();
    // No $ column header.
    const headers = screen
      .getAllByRole("columnheader")
      .map((h) => h.textContent ?? "");
    for (const h of headers) {
      expect(/\$/i.test(h), `banned $ header: ${h}`).toBe(false);
    }
  });

  it("marks the best line with the best badge", () => {
    render(<ExecutionTrail {...makeProps()} />);
    const bestBadges = screen.getAllByTestId("best-badge");
    expect(bestBadges.length).toBeGreaterThan(0);
    // The best book name (Kalshi) appears in the best row.
    const bestRow = screen.getByTestId("best-line-row");
    expect(bestRow.textContent).toContain("Kalshi");
  });

  it("best line row has emerald text class", () => {
    const { container } = render(<ExecutionTrail {...makeProps()} />);
    const emeraldCells = container.querySelectorAll(".text-emerald-400");
    expect(emeraldCells.length).toBeGreaterThan(0);
  });

  it("PM venue shows PM label", () => {
    render(<ExecutionTrail {...makeProps()} />);
    expect(screen.getByText("PM")).toBeTruthy();
  });

  it("shows unavailable message when bookLines is empty", () => {
    render(<ExecutionTrail {...makeProps({ bookLines: [] })} />);
    // Empty bookLines -> Unavailable component shows "No book lines available"
    expect(screen.getByText(/No book lines available/i)).toBeTruthy();
    // No book-lines-table should be rendered.
    expect(screen.queryByTestId("book-lines-table")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Devig section
// ---------------------------------------------------------------------------

describe("ExecutionTrail -- devig section", () => {
  it("renders the devig section", () => {
    render(<ExecutionTrail {...makeProps()} />);
    expect(screen.getByTestId("devig-section")).toBeTruthy();
  });

  it("renders fair_prob as a percentage (no $)", () => {
    render(<ExecutionTrail {...makeProps()} />);
    // 0.518 -> "51.8%"
    expect(screen.getByText("51.8%")).toBeTruthy();
  });

  it("renders vig_pct as a percentage", () => {
    render(<ExecutionTrail {...makeProps()} />);
    // 0.045 -> "4.5%"
    expect(screen.getByText("4.5%")).toBeTruthy();
  });

  it("shows 'prob ratio -- no $' label in devig section", () => {
    render(<ExecutionTrail {...makeProps()} />);
    expect(screen.getByText(/prob ratio -- no \$/i)).toBeTruthy();
  });

  it("shows fallback when devig is null", () => {
    render(<ExecutionTrail {...makeProps({ devig: null })} />);
    expect(screen.getByText(/Devig not computed/i)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Decision trail
// ---------------------------------------------------------------------------

describe("ExecutionTrail -- decision trail", () => {
  it("renders the decision trail section", () => {
    render(<ExecutionTrail {...makeProps()} />);
    expect(screen.getByTestId("decision-trail")).toBeTruthy();
  });

  it("shows 'bet' decision label for decision=bet", () => {
    render(<ExecutionTrail {...makeProps({ decision: "bet" })} />);
    const label = screen.getByTestId("decision-label");
    expect(label.textContent).toContain("bet");
  });

  it("shows 'no_bet' decision label when decision=no_bet", () => {
    render(<ExecutionTrail {...makeProps({ decision: "no_bet", stakeUnits: null })} />);
    const label = screen.getByTestId("decision-label");
    expect(label.textContent).toContain("no_bet");
  });

  it("shows stake in units (no $) for bet decision", () => {
    render(<ExecutionTrail {...makeProps()} />);
    const stake = screen.getByTestId("stake-units");
    expect(stake.textContent).toContain("1.25u");
    expect(stake.textContent).not.toContain("$");
  });

  it("shows no_bet in stake cell when decision is no_bet", () => {
    render(<ExecutionTrail {...makeProps({ decision: "no_bet", stakeUnits: null })} />);
    const stake = screen.getByTestId("stake-units");
    expect(stake.textContent).toContain("no_bet");
  });

  it("renders tier badge with correct token class", () => {
    const { container } = render(<ExecutionTrail {...makeProps({ tier: "A" })} />);
    // tierBadgeClass("A") = "border-tier-a text-tier-a bg-tier-a/10"
    const tierBadge = container.querySelector('[data-testid="tier-badge"] span');
    expect(tierBadge?.className).toContain("text-tier-a");
  });

  it("shows tier='S' with tier-s token classes", () => {
    const { container } = render(<ExecutionTrail {...makeProps({ tier: "S" })} />);
    const tierBadge = container.querySelector('[data-testid="tier-badge"] span');
    expect(tierBadge?.className).toContain("text-tier-s");
  });

  it("renders model prob as percentage", () => {
    render(<ExecutionTrail {...makeProps({ modelProb: 0.54 })} />);
    const prob = screen.getByTestId("model-prob");
    expect(prob.textContent).toContain("54.0%");
  });

  it("shows INSUFFICIENT_DATA CLV status in amber", () => {
    const { container } = render(
      <ExecutionTrail {...makeProps({ clvStatus: "INSUFFICIENT_DATA" })} />,
    );
    const clv = screen.getByTestId("clv-status");
    expect(clv.textContent).toContain("INSUFFICIENT_DATA");
    // Must be amber-colored (text-amber-600).
    const amber = container.querySelector('[data-testid="clv-status"] .text-amber-600');
    expect(amber).toBeTruthy();
  });

  it("shows null clvStatus as INSUFFICIENT_DATA (honest fallback)", () => {
    render(<ExecutionTrail {...makeProps({ clvStatus: null })} />);
    const clv = screen.getByTestId("clv-status");
    expect(clv.textContent).toContain("INSUFFICIENT_DATA");
  });

  it("shows real clv_status string when not INSUFFICIENT_DATA", () => {
    render(<ExecutionTrail {...makeProps({ clvStatus: "true_close" })} />);
    const clv = screen.getByTestId("clv-status");
    expect(clv.textContent).toContain("true_close");
  });

  it("renders decisionNote when provided", () => {
    render(
      <ExecutionTrail
        {...makeProps({ decisionNote: "Tier-A edge vs market probability." })}
      />,
    );
    expect(screen.getByTestId("decision-note").textContent).toContain(
      "Tier-A edge vs market probability.",
    );
  });
});

// ---------------------------------------------------------------------------
// Real-money DENY note
// ---------------------------------------------------------------------------

describe("ExecutionTrail -- real-money DENY note", () => {
  it("renders the DENY note when bookLines provided", () => {
    render(<ExecutionTrail {...makeProps()} />);
    expect(screen.getByTestId("real-money-deny")).toBeTruthy();
    expect(screen.getByText(/REAL-MONEY DENY/i)).toBeTruthy();
  });

  it("renders the DENY note even in the empty-bookLines state", () => {
    render(<ExecutionTrail {...makeProps({ bookLines: [] })} />);
    expect(screen.getByTestId("real-money-deny")).toBeTruthy();
  });

  it("DENY note mentions units and no dollar column", () => {
    render(<ExecutionTrail {...makeProps()} />);
    const note = screen.getByTestId("real-money-deny");
    expect(/units/i.test(note.textContent ?? "")).toBe(true);
    expect(/paper/i.test(note.textContent ?? "")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Honest states: loading, error, empty
// ---------------------------------------------------------------------------

describe("ExecutionTrail -- honest degraded states", () => {
  it("loading=true shows checking... (never stale data)", () => {
    render(<ExecutionTrail {...makeProps({ loading: true })} />);
    expect(screen.getByText(/checking/i)).toBeTruthy();
    // Must NOT render book lines while loading.
    expect(screen.queryByTestId("book-lines-table")).toBeNull();
  });

  it("error prop -> renders Unavailable + DENY note, no crash", () => {
    render(
      <ExecutionTrail {...makeProps({ error: "feed down", bookLines: [] })} />,
    );
    expect(screen.getByText(/feed down/i)).toBeTruthy();
    expect(screen.getByTestId("real-money-deny")).toBeTruthy();
  });

  it("empty bookLines -> unavailable message shown, decision trail still rendered", () => {
    render(<ExecutionTrail {...makeProps({ bookLines: [] })} />);
    expect(screen.getByText(/No book lines available/i)).toBeTruthy();
    // Decision trail must still render even with no book data.
    expect(screen.getByTestId("decision-trail")).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// No $ in rendered output (HONESTY RAIL)
// ---------------------------------------------------------------------------

describe("ExecutionTrail -- no $ in rendered output", () => {
  it("full props: no $ amount anywhere in rendered output", () => {
    const { container } = render(<ExecutionTrail {...makeProps()} />);
    noDollar(container);
  });

  it("no_bet path: no $ amount anywhere in rendered output", () => {
    const { container } = render(
      <ExecutionTrail {...makeProps({ decision: "no_bet", stakeUnits: null })} />,
    );
    noDollar(container);
  });

  it("empty bookLines: no $ amount", () => {
    const { container } = render(
      <ExecutionTrail {...makeProps({ bookLines: [] })} />,
    );
    noDollar(container);
  });

  it("error state: no $ amount", () => {
    const { container } = render(
      <ExecutionTrail {...makeProps({ error: "no feed", bookLines: [] })} />,
    );
    noDollar(container);
  });
});

// ---------------------------------------------------------------------------
// No $ in source files (HONESTY RAIL)
// ---------------------------------------------------------------------------

describe("NO $ field in execution source files", () => {
  it("no source file emits a $/pnl/roi/payout field", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const root = join(dir, ".."); // execution/
    const files = readdirSync(root).filter(
      (f) => (f.endsWith(".ts") || f.endsWith(".tsx")) && !f.endsWith(".test.tsx"),
    );
    // A real $ AMOUNT ($ next to a digit) or a named $ money field is banned.
    // Prose like "no $" or "no $ column" is explicitly allowed (honesty rail).
    const banned = /\$\s*\d|\d\s*\$|\bpnl\b|\b(pnl|roi|payout)\s*[:=]/i;
    expect(files.length).toBeGreaterThan(0);
    for (const f of files) {
      const code = readFileSync(join(root, f), "utf8");
      expect(banned.test(code), `banned $ token in ${f}`).toBe(false);
    }
  });
});
