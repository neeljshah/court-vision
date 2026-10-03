import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { BetCard, type BetCardData } from "../BetCard";
import { ModelVsMarketBar, type ModelVsMarketBarProps } from "../ModelVsMarketBar";
import { cardToBetCardData } from "../BestBetsBoardHelpers";
import type { BestBetsCard } from "@/lib/p5api";
import mlbBoard from "@/public/demo-data/api_bestbets_board_sport_mlb.json";

afterEach(cleanup);

type Input = Partial<Omit<BetCardData, "model_prob" | "confidence">> & {
  model_prob?: number | null;
  confidence?: number | null;
};

function card(overrides: Input = {}): BetCardData {
  // Nullable wire confidence exercises the renderer while its older public
  // TypeScript contract still declares confidence as a required number.
  return {
    game_id: "availability-fixture", sport: "mlb", matchup: "Home vs Away",
    market_type: "moneyline", side: "home", model_prob: 0.6, market_prob: 0.5,
    best_book: "pinnacle", best_odds: 2, all_books: [], edge_vs_market: 0.1,
    units: 1, tier: "B", confidence: 0.6, clv: null, clv_is_proxy: false,
    status: "pregame", ...overrides,
  } as BetCardData;
}

function bar(overrides: Partial<ModelVsMarketBarProps> = {}) {
  return <ModelVsMarketBar
    model_prob={0.6} market_prob={0.5} divergence={0.1}
    divergence_label="+10.0pp" divergence_is_signal framing="bet"
    {...overrides}
  />;
}

function unavailableProbability(kind: "Model" | "Market") {
  expect(screen.getByLabelText(new RegExp(`^${kind} probability unavailable$`, "i"))).toHaveTextContent("--");
  expect(screen.queryByRole("meter", { name: kind === "Model" ? /^model probability/i : /market probability/i })).not.toBeInTheDocument();
}

function unavailableDivergence() {
  expect(screen.getByTestId("divergence-chip")).toHaveTextContent(/unavailable/i);
  expect(screen.getByTestId("divergence-chip")).not.toHaveTextContent(/\d.*pp/);
}

describe("BetCard probability availability", () => {
  it("keeps a valid market when the model is missing without reporting divergence", () => {
    render(<BetCard card={card({ model_prob: null })} />);
    unavailableProbability("Model");
    expect(screen.getByRole("meter", { name: /market probability/i })).toHaveAttribute("aria-valuenow", "50");
    unavailableDivergence();
  });

  it("keeps a valid model when the market is missing without fabricating a zero market", () => {
    render(<BetCard card={card({ market_prob: null })} />);
    unavailableProbability("Market");
    expect(screen.getByRole("meter", { name: /^model probability/i })).toHaveAttribute("aria-valuenow", "60");
    unavailableDivergence();
  });

  it("keeps both valid probabilities but does not fabricate missing reported divergence", () => {
    render(<BetCard card={card({ edge_vs_market: null })} />);
    expect(screen.getAllByRole("meter")).toHaveLength(2);
    unavailableDivergence();
  });

  it.each([
    { kind: "Model" as const, override: { model_prob: NaN } },
    { kind: "Model" as const, override: { model_prob: Infinity } },
    { kind: "Market" as const, override: { market_prob: -0.1 } },
    { kind: "Market" as const, override: { market_prob: 1.1 } },
  ])("marks invalid $kind probability unavailable instead of clamping it into a meter", ({ kind, override }) => {
    render(<BetCard card={card(override)} />);
    unavailableProbability(kind);
    expect(screen.getAllByRole("meter")).toHaveLength(1);
    unavailableDivergence();
  });

  it.each([0, 1])("preserves the valid endpoint probability %s", (value) => {
    render(bar({ model_prob: value, market_prob: 1 - value, divergence: value - (1 - value) }));
    expect(screen.getByRole("meter", { name: /^model probability/i })).toHaveAttribute("aria-valuenow", String(value * 100));
    expect(screen.getByRole("meter", { name: /market probability/i })).toHaveAttribute("aria-valuenow", String((1 - value) * 100));
    expect(screen.getByTestId("model-bar-row")).toHaveTextContent(`${(value * 100).toFixed(1)}%`);
    expect(screen.getByTestId("market-bar-row")).toHaveTextContent(`${((1 - value) * 100).toFixed(1)}%`);
    expect(screen.getByTestId("model-bar")).toHaveStyle({ width: `${value * 100}%` });
    expect(screen.getByTestId("market-bar")).toHaveStyle({ width: `${(1 - value) * 100}%` });
    expect(screen.queryByLabelText(/probability unavailable/i)).not.toBeInTheDocument();
  });

  it("does not turn absent confidence, zero reported stake or untiered status into recommendations", () => {
    render(<BetCard card={card({ confidence: null, units: 0, tier: null })} />);
    expect(screen.queryByTestId("confidence-strip")).not.toBeInTheDocument();
    expect(screen.getByTestId("units-value")).toHaveTextContent("0.0 UNITS");
    expect(screen.getByLabelText("untiered")).toHaveTextContent("--");
    expect(screen.getAllByRole("meter")).toHaveLength(2);
  });

  it("ignores a numeric-looking label when the supplied divergence is nonfinite", () => {
    render(bar({ divergence: NaN, divergence_label: "+9.9pp" }));
    expect(screen.getAllByRole("meter")).toHaveLength(2);
    unavailableDivergence();
  });

  it("preserves the actual public MLB line-only card through the board mapper", () => {
    const wire = mlbBoard.cards.find((row) => row.model_prob === null && row.market_prob != null && row.market_type !== "prop");
    expect(wire).toBeDefined();
    if (!wire) throw new Error("Public MLB fixture lacks a line-only card");
    render(<BetCard card={cardToBetCardData(wire as BestBetsCard)} />);
    unavailableProbability("Model");
    expect(screen.getByRole("meter", { name: /market probability/i })).toHaveAttribute("aria-valuenow", String(Math.round(wire.market_prob! * 100)));
    expect(screen.queryByTestId("confidence-strip")).not.toBeInTheDocument();
    expect(screen.getByTestId("units-value")).toHaveTextContent("0.0 UNITS");
    expect(screen.getByLabelText("untiered")).toHaveTextContent("--");
    unavailableDivergence();
  });
});
