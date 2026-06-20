// card-depth.test.tsx -- vitest per-component tests for WS7 card-depth layer.
//
// ACCEPTANCE CRITERIA:
//   1. ModelVsMarketBar renders two opposing bars with a labeled divergence
//      (no 'edge'/'profit' wording, no '$')
//   2. LineComparison highlights the best line among multiple books and renders
//      devigged market prob
//   3. cardDepth helper returns 'descriptive/no-bet' when game_done=true or
//      degenerate_model=true
//   4. CLV absent -> INSUFFICIENT_DATA, never 0

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { ModelVsMarketBar } from "../ModelVsMarketBar";
import { LineComparison, type LineComparisonEntry } from "../LineComparison";
import {
  resolveCardFraming,
  formatClv,
  formatDivergence,
  isDivergenceSignal,
  devigProb,
  findBestLine,
  type ResolveFramingInput,
} from "../cardDepth";

// ---------------------------------------------------------------------------
// Helpers / fixtures
// ---------------------------------------------------------------------------

function makeFramingInput(
  overrides: Partial<ResolveFramingInput> = {},
): ResolveFramingInput {
  return {
    game_done: false,
    degenerate_model: false,
    model_prob: 0.55,
    market_prob: 0.50,
    clv: null,
    clv_is_proxy: false,
    ...overrides,
  };
}

function makeBooks(overrides: Partial<LineComparisonEntry>[] = []): LineComparisonEntry[] {
  const defaults: LineComparisonEntry[] = [
    { book: "DraftKings", odds: 1.91, clv: null },
    { book: "FanDuel", odds: 1.95, clv: null },
    { book: "BetMGM", odds: 1.87, clv: null },
  ];
  return defaults.map((d, i) => ({ ...d, ...(overrides[i] ?? {}) }));
}

// ---------------------------------------------------------------------------
// 1. ModelVsMarketBar -- two opposing bars + labeled divergence
// ---------------------------------------------------------------------------

describe("ModelVsMarketBar -- two opposing bars with labeled divergence", () => {
  it("renders model and market bar elements", () => {
    const { container } = render(
      <ModelVsMarketBar
        model_prob={0.55}
        market_prob={0.50}
        divergence={0.05}
        divergence_label="+5.0pp"
        divergence_is_signal={true}
        framing="bet"
      />,
    );
    expect(container.querySelector("[data-testid='model-bar']")).not.toBeNull();
    expect(container.querySelector("[data-testid='market-bar']")).not.toBeNull();
  });

  it("model bar has a different width than market bar when probs differ", () => {
    const { container } = render(
      <ModelVsMarketBar
        model_prob={0.65}
        market_prob={0.45}
        divergence={0.20}
        divergence_label="+20.0pp"
        divergence_is_signal={true}
        framing="bet"
      />,
    );
    const modelBar = container.querySelector("[data-testid='model-bar']") as HTMLElement;
    const marketBar = container.querySelector("[data-testid='market-bar']") as HTMLElement;
    expect(modelBar?.style.width).not.toBe(marketBar?.style.width);
  });

  it("divergence chip renders with label text", () => {
    const { container } = render(
      <ModelVsMarketBar
        model_prob={0.55}
        market_prob={0.50}
        divergence={0.05}
        divergence_label="+5.0pp"
        divergence_is_signal={true}
        framing="bet"
      />,
    );
    const chip = container.querySelector("[data-testid='divergence-chip']");
    expect(chip).not.toBeNull();
    expect(chip?.textContent).toContain("+5.0pp");
  });

  it("divergence chip aria-label says 'calibrated divergence' and 'not an edge or profit claim'", () => {
    const { container } = render(
      <ModelVsMarketBar
        model_prob={0.55}
        market_prob={0.50}
        divergence={0.05}
        divergence_label="+5.0pp"
        divergence_is_signal={true}
        framing="bet"
      />,
    );
    const chip = container.querySelector("[data-testid='divergence-chip']");
    const ariaLabel = (chip?.getAttribute("aria-label") ?? "").toLowerCase();
    expect(ariaLabel).toContain("calibrated divergence");
    expect(ariaLabel).toContain("not an edge or profit claim");
  });

  it("no 'edge' or 'profit' word appears in textContent outside disclaimer", () => {
    const { container } = render(
      <ModelVsMarketBar
        model_prob={0.58}
        market_prob={0.48}
        divergence={0.10}
        divergence_label="+10.0pp"
        divergence_is_signal={true}
        framing="bet"
      />,
    );
    const text = (container.textContent ?? "").toLowerCase();
    // The honesty footnote may say "not an edge or profit claim" or "not a profit claim".
    // That's OK as a disclaimer. We check for standalone 'edge'/'profit' outside disclaimer.
    // Strip all honesty disclaimer text forms to isolate positive-framing violations.
    const withoutDisclaimer = text
      .replace(/not an? (?:edge or )?profit(?: claim)?/g, "")
      .replace(/calibrated divergence/g, "");
    expect(withoutDisclaimer).not.toMatch(/\bedge\b/);
    expect(withoutDisclaimer).not.toMatch(/\bprofit\b/);
  });

  it("no '$<digit>' pattern in textContent", () => {
    const { container } = render(
      <ModelVsMarketBar
        model_prob={0.55}
        market_prob={0.50}
        divergence={0.05}
        divergence_label="+5.0pp"
        divergence_is_signal={true}
        framing="bet"
      />,
    );
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("descriptive framing shows neutral note and hides divergence chip", () => {
    const { container } = render(
      <ModelVsMarketBar
        model_prob={0.55}
        market_prob={0.50}
        divergence={0.05}
        divergence_label="+5.0pp"
        divergence_is_signal={true}
        framing="descriptive"
      />,
    );
    expect(container.querySelector("[data-testid='descriptive-note']")).not.toBeNull();
    expect(container.querySelector("[data-testid='divergence-chip']")).toBeNull();
  });

  it("negative divergence does not crash and renders a valid label", () => {
    const { container } = render(
      <ModelVsMarketBar
        model_prob={0.42}
        market_prob={0.48}
        divergence={-0.06}
        divergence_label="-6.0pp"
        divergence_is_signal={true}
        framing="bet"
      />,
    );
    const chip = container.querySelector("[data-testid='divergence-chip']");
    expect(chip?.textContent).toContain("-6.0pp");
  });

  it("both bars have role='meter' with aria-valuenow", () => {
    const { container } = render(
      <ModelVsMarketBar
        model_prob={0.55}
        market_prob={0.50}
        divergence={0.05}
        divergence_label="+5.0pp"
        divergence_is_signal={true}
        framing="bet"
      />,
    );
    const meters = container.querySelectorAll("[role='meter']");
    expect(meters.length).toBe(2);
    for (const m of Array.from(meters)) {
      expect(m.getAttribute("aria-valuenow")).not.toBeNull();
    }
  });

  it("confidence strip renders when confidence is provided and framing=bet", () => {
    const { container } = render(
      <ModelVsMarketBar
        model_prob={0.55}
        market_prob={0.50}
        divergence={0.05}
        divergence_label="+5.0pp"
        divergence_is_signal={true}
        framing="bet"
        confidence={0.72}
      />,
    );
    expect(container.querySelector("[data-testid='confidence-strip']")).not.toBeNull();
  });

  it("confidence strip hidden in descriptive framing", () => {
    const { container } = render(
      <ModelVsMarketBar
        model_prob={0.55}
        market_prob={0.50}
        divergence={0.05}
        divergence_label="+5.0pp"
        divergence_is_signal={true}
        framing="descriptive"
        confidence={0.72}
      />,
    );
    expect(container.querySelector("[data-testid='confidence-strip']")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 2. LineComparison -- best line highlighted, devigged market prob rendered
// ---------------------------------------------------------------------------

describe("LineComparison -- best line highlighted + devigged prob", () => {
  it("renders a row for each book", () => {
    const { container } = render(<LineComparison books={makeBooks()} />);
    const rows = container.querySelectorAll("[data-testid='book-line-row'], [data-testid='best-line-row']");
    expect(rows.length).toBe(3);
  });

  it("highlights the book with the highest decimal odds as best", () => {
    // FanDuel has 1.95 (highest)
    const { container } = render(<LineComparison books={makeBooks()} />);
    const bestRow = container.querySelector("[data-testid='best-line-row']");
    expect(bestRow).not.toBeNull();
    expect(bestRow?.textContent).toContain("FanDuel");
  });

  it("best row includes 'best' badge text", () => {
    const { container } = render(<LineComparison books={makeBooks()} />);
    const bestRow = container.querySelector("[data-testid='best-line-row']");
    expect(bestRow?.textContent?.toLowerCase()).toContain("best");
  });

  it("best row's aria-label includes 'best line'", () => {
    const { container } = render(<LineComparison books={makeBooks()} />);
    const bestRow = container.querySelector("[data-testid='best-line-row']");
    const ariaLabel = (bestRow?.getAttribute("aria-label") ?? "").toLowerCase();
    expect(ariaLabel).toContain("best line");
  });

  it("renders devigged market probability for best line", () => {
    const { container } = render(<LineComparison books={makeBooks()} />);
    const bestDevig = container.querySelector("[data-testid='best-line-devig']");
    expect(bestDevig).not.toBeNull();
    // FanDuel at 1.95: devig ~= 1/1.95 = 51.3% (single-side). Check it contains a pct.
    expect(bestDevig?.textContent).toMatch(/\d+\.\d+%/);
  });

  it("CLV null renders INSUFFICIENT_DATA, not 0", () => {
    const { container } = render(<LineComparison books={makeBooks()} />);
    const clvCells = container.querySelectorAll("[data-testid='clv-insufficient']");
    expect(clvCells.length).toBeGreaterThan(0);
    for (const cell of Array.from(clvCells)) {
      expect(cell.textContent).toContain("INSUFFICIENT_DATA");
      expect(cell.textContent).not.toBe("0");
      expect(cell.textContent).not.toBe("0.0%");
    }
  });

  it("renders numeric CLV when provided", () => {
    const books: LineComparisonEntry[] = [
      { book: "DraftKings", odds: 1.91, clv: 0.02 },
      { book: "FanDuel", odds: 1.95, clv: -0.01 },
    ];
    const { container } = render(<LineComparison books={books} />);
    const clvValues = container.querySelectorAll("[data-testid='clv-value']");
    expect(clvValues.length).toBe(2);
  });

  it("shows unavailable when books list is empty", () => {
    render(<LineComparison books={[]} />);
    // Unavailable component renders with role='status' and 'unavailable' text
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("no '$<digit>' in textContent", () => {
    const { container } = render(<LineComparison books={makeBooks()} />);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("renders American odds format (not decimal)", () => {
    const books: LineComparisonEntry[] = [
      { book: "DraftKings", odds: 1.91, clv: null },
    ];
    const { container } = render(<LineComparison books={books} />);
    // 1.91 -> -110
    expect(container.textContent).toContain("-110");
  });

  it("two-outcome devig gives lower implied prob when opposing_odds provided", () => {
    // With opposing_odds the vig is split; single-side devig gives a higher raw prob.
    // odds=1.91 single-side: ~51.3%; with opposing_odds=1.91 devig: 50.0%
    const books: LineComparisonEntry[] = [
      { book: "DraftKings", odds: 1.91, clv: null },
    ];
    const { container: single } = render(<LineComparison books={books} />);
    const { container: two } = render(
      <LineComparison books={books} opposing_odds={1.91} />,
    );
    const singleDevig = single.querySelector("[data-testid='best-line-devig']")?.textContent ?? "";
    const twoDevig = two.querySelector("[data-testid='best-line-devig']")?.textContent ?? "";
    // Two-outcome devig should give lower or equal prob than single-side (vig spread)
    const singlePct = parseFloat(singleDevig);
    const twoPct = parseFloat(twoDevig);
    expect(twoPct).toBeLessThanOrEqual(singlePct + 0.5); // within 0.5pp tolerance
  });
});

// ---------------------------------------------------------------------------
// 3. cardDepth helper -- resolveCardFraming
// ---------------------------------------------------------------------------

describe("cardDepth -- resolveCardFraming: DONE -> descriptive", () => {
  it("game_done=true returns framing='descriptive'", () => {
    const result = resolveCardFraming(makeFramingInput({ game_done: true }));
    expect(result.framing).toBe("descriptive");
  });

  it("game_done=true has a non-null descriptive_reason", () => {
    const result = resolveCardFraming(makeFramingInput({ game_done: true }));
    expect(result.descriptive_reason).not.toBeNull();
    expect((result.descriptive_reason ?? "").length).toBeGreaterThan(0);
  });

  it("game_done=true descriptive_reason mentions 'ended' or 'done' or 'settled'", () => {
    const result = resolveCardFraming(makeFramingInput({ game_done: true }));
    const reason = (result.descriptive_reason ?? "").toLowerCase();
    expect(
      reason.includes("ended") || reason.includes("done") || reason.includes("settled"),
    ).toBe(true);
  });
});

describe("cardDepth -- resolveCardFraming: degenerate_model -> descriptive", () => {
  it("degenerate_model=true returns framing='descriptive'", () => {
    const result = resolveCardFraming(makeFramingInput({ degenerate_model: true }));
    expect(result.framing).toBe("descriptive");
  });

  it("degenerate_model=true has a non-null descriptive_reason", () => {
    const result = resolveCardFraming(makeFramingInput({ degenerate_model: true }));
    expect(result.descriptive_reason).not.toBeNull();
  });

  it("degenerate_model=true descriptive_reason mentions 'degenerate' or 'calibration'", () => {
    const result = resolveCardFraming(makeFramingInput({ degenerate_model: true }));
    const reason = (result.descriptive_reason ?? "").toLowerCase();
    expect(
      reason.includes("degenerate") || reason.includes("calibration"),
    ).toBe(true);
  });

  it("model_prob=0 (boundary degenerate) returns framing='descriptive'", () => {
    const result = resolveCardFraming(
      makeFramingInput({ model_prob: 0, degenerate_model: false }),
    );
    expect(result.framing).toBe("descriptive");
  });

  it("model_prob=1 (boundary degenerate) returns framing='descriptive'", () => {
    const result = resolveCardFraming(
      makeFramingInput({ model_prob: 1, degenerate_model: false }),
    );
    expect(result.framing).toBe("descriptive");
  });

  it("model_prob=NaN returns framing='descriptive'", () => {
    const result = resolveCardFraming(
      makeFramingInput({ model_prob: NaN, degenerate_model: false }),
    );
    expect(result.framing).toBe("descriptive");
  });
});

describe("cardDepth -- resolveCardFraming: normal inputs -> framing='bet'", () => {
  it("active game + valid model -> framing='bet'", () => {
    const result = resolveCardFraming(makeFramingInput());
    expect(result.framing).toBe("bet");
  });

  it("framing='bet' has null descriptive_reason", () => {
    const result = resolveCardFraming(makeFramingInput());
    expect(result.descriptive_reason).toBeNull();
  });

  it("divergence is computed as model_prob - market_prob", () => {
    const result = resolveCardFraming(
      makeFramingInput({ model_prob: 0.55, market_prob: 0.48 }),
    );
    expect(result.divergence).toBeCloseTo(0.07, 4);
  });

  it("divergence_is_signal=true when |div| >= 0.05", () => {
    const result = resolveCardFraming(
      makeFramingInput({ model_prob: 0.55, market_prob: 0.48 }),
    );
    expect(result.divergence_is_signal).toBe(true);
  });

  it("divergence_is_signal=false when |div| < 0.05", () => {
    const result = resolveCardFraming(
      makeFramingInput({ model_prob: 0.52, market_prob: 0.50 }),
    );
    expect(result.divergence_is_signal).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 4. CLV: absent -> INSUFFICIENT_DATA, never 0
// ---------------------------------------------------------------------------

describe("cardDepth -- CLV: null always yields INSUFFICIENT_DATA", () => {
  it("clv=null -> clv_label = 'INSUFFICIENT_DATA'", () => {
    const result = resolveCardFraming(makeFramingInput({ clv: null }));
    expect(result.clv_label).toBe("INSUFFICIENT_DATA");
  });

  it("clv=null -> clv_display is null", () => {
    const result = resolveCardFraming(makeFramingInput({ clv: null }));
    expect(result.clv_display).toBeNull();
  });

  it("clv=null label is NOT '0' or '0.0%'", () => {
    const result = resolveCardFraming(makeFramingInput({ clv: null }));
    expect(result.clv_label).not.toBe("0");
    expect(result.clv_label).not.toBe("0.0%");
    expect(result.clv_label).not.toBe("+0.0%");
  });

  it("clv=0 (provided zero) -> label contains '0.0%' but NOT 'INSUFFICIENT_DATA'", () => {
    // A real CLV of 0 is different from null; it should be shown as a numeric value.
    const result = resolveCardFraming(makeFramingInput({ clv: 0 }));
    expect(result.clv_label).not.toBe("INSUFFICIENT_DATA");
    expect(result.clv_label).toContain("0.0%");
  });

  it("clv=0.032 formats as '+3.2%'", () => {
    const result = resolveCardFraming(makeFramingInput({ clv: 0.032 }));
    expect(result.clv_label).toContain("+3.2%");
  });

  it("clv=-0.015 formats as '-1.5%'", () => {
    const result = resolveCardFraming(makeFramingInput({ clv: -0.015 }));
    expect(result.clv_label).toContain("-1.5%");
  });

  it("clv_is_proxy=true appends (proxy) to label", () => {
    const result = resolveCardFraming(
      makeFramingInput({ clv: 0.02, clv_is_proxy: true }),
    );
    expect(result.clv_label.toLowerCase()).toContain("proxy");
  });
});

// ---------------------------------------------------------------------------
// 5. Pure helper unit tests
// ---------------------------------------------------------------------------

describe("formatClv", () => {
  it("null -> 'INSUFFICIENT_DATA'", () => {
    expect(formatClv(null, false)).toBe("INSUFFICIENT_DATA");
  });

  it("positive -> '+X.Y%'", () => {
    expect(formatClv(0.032, false)).toBe("+3.2%");
  });

  it("negative -> '-X.Y%'", () => {
    expect(formatClv(-0.015, false)).toBe("-1.5%");
  });

  it("proxy appends (proxy)", () => {
    expect(formatClv(0.02, true)).toContain("(proxy)");
  });
});

describe("formatDivergence", () => {
  it("positive -> '+X.Ypp'", () => {
    expect(formatDivergence(0.05)).toBe("+5.0pp");
  });

  it("negative -> '-X.Ypp'", () => {
    expect(formatDivergence(-0.08)).toBe("-8.0pp");
  });

  it("zero -> '+0.0pp'", () => {
    expect(formatDivergence(0)).toBe("+0.0pp");
  });
});

describe("isDivergenceSignal", () => {
  it("0.05 -> true (at threshold)", () => {
    expect(isDivergenceSignal(0.05)).toBe(true);
  });

  it("-0.06 -> true (negative signal)", () => {
    expect(isDivergenceSignal(-0.06)).toBe(true);
  });

  it("0.03 -> false (below threshold)", () => {
    expect(isDivergenceSignal(0.03)).toBe(false);
  });

  it("0 -> false", () => {
    expect(isDivergenceSignal(0)).toBe(false);
  });
});

describe("devigProb", () => {
  it("single-side: 1.91 -> ~51.8%", () => {
    // 1 / 1.91 = 0.5236
    expect(devigProb(1.91)).toBeCloseTo(0.5236, 2);
  });

  it("two-outcome equal odds: 1.91 vs 1.91 -> ~50%", () => {
    // Balanced vig -> 50/50
    expect(devigProb(1.91, 1.91)).toBeCloseTo(0.5, 2);
  });

  it("degenerate odds <= 1 -> returns 0.5 guard", () => {
    expect(devigProb(1)).toBe(0.5);
    expect(devigProb(0)).toBe(0.5);
  });

  it("result is clamped to [0.01, 0.99]", () => {
    const r = devigProb(100, 1.01);
    expect(r).toBeGreaterThanOrEqual(0.01);
    expect(r).toBeLessThanOrEqual(0.99);
  });
});

describe("findBestLine", () => {
  it("empty array -> -1", () => {
    expect(findBestLine([])).toBe(-1);
  });

  it("single entry -> index 0", () => {
    expect(findBestLine([{ book: "DK", odds: 1.91 }])).toBe(0);
  });

  it("returns index of highest odds", () => {
    const books = [
      { book: "DK", odds: 1.91 },
      { book: "FD", odds: 1.95 },
      { book: "BetMGM", odds: 1.87 },
    ];
    expect(findBestLine(books)).toBe(1);
  });

  it("tie -> first occurrence wins", () => {
    const books = [
      { book: "DK", odds: 1.95 },
      { book: "FD", odds: 1.95 },
    ];
    expect(findBestLine(books)).toBe(0);
  });
});
