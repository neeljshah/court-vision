import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { SlateCards } from "../SlateCards";

const { getPredict, bestbets } = vi.hoisted(() => ({
  getPredict: vi.fn(), bestbets: vi.fn(),
}));
vi.mock("@/lib/api", () => ({
  api: { getPredict, bestbets },
  isUnavailable: (value: { status?: string } | null) => value?.status === "unavailable",
}));
vi.mock("@/lib/board", async (original) => ({
  ...(await original<typeof import("@/lib/board")>()),
  fetchSlate: vi.fn().mockResolvedValue(null),
}));
vi.mock("../SlateAgeBar", () => ({ SlateAgeBar: () => null }));

const record = {
  sport: "mlb", game_id: "fixture", home: "Home", away: "Away",
  tipoff: null, pregame_probs: { home_ml: 0.6, away_ml: 0.4 },
  markets: [], produced_at: null, leak_guard: { in_sample: false },
};
const selected = {
  game_id: record.game_id, status: "ok",
  best_bets: [{ decision: "bet", tier: "B", stake_units: 1, market_type: "moneyline", side: "home" }],
};

beforeEach(() => {
  vi.useFakeTimers();
  getPredict.mockImplementation(async (sport: string) => ({
    status: "ok", sport, generated_at: null,
    predictions: sport === "mlb" ? [record] : [],
  }));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("Games decision availability", () => {
  it.each([
    null,
    { status: "unavailable", reason: "snapshot file missing" },
    { status: "ok" },
    { status: "ok", games: {} },
    { status: "error", games: [selected] },
  ])("keeps unavailable or invalid feeds distinct from a reported rejection: %j", async (feed) => {
    bestbets.mockResolvedValue(feed);
    await act(async () => { render(<SlateCards />); });
    expect(screen.getByText("decision unavailable")).toBeInTheDocument();
    expect(screen.getByText(/Decision unavailable means no usable decision was received/)).toBeVisible();
    expect(screen.queryByText(/below floor|^no bet reported$/i)).toBeNull();
    expect(screen.queryByLabelText(/best bet: tier/i)).toBeNull();
  });

  it.each([
    { status: "unavailable", reason: "feed offline" },
    { status: "ok", games: [null] },
    { status: "ok", games: [selected, null] },
    { status: "ok", games: [{ ...selected, game_id: 42 }] },
    { status: "ok", games: [{ ...selected, game_id: " " }] },
    { status: "ok", games: [{ ...selected, best_bets: [null] }] },
    { status: "ok", games: [{ ...selected, best_bets: [{ decision: "unknown" }] }] },
  ])("clears an old selection on failure and recovers from %j", async (failure) => {
    bestbets.mockResolvedValue({ status: "ok", games: [selected] });
    await act(async () => { render(<SlateCards />); });
    expect(screen.getByLabelText("best bet: tier B, 1.00 units")).toBeInTheDocument();

    bestbets.mockResolvedValue(failure);
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    expect(screen.getByText("decision unavailable")).toBeInTheDocument();
    expect(screen.queryByLabelText(/best bet: tier/i)).toBeNull();
    expect(screen.queryByText(/below floor|^no bet reported$/i)).toBeNull();

    bestbets.mockResolvedValue({ status: "ok", games: [{ ...selected, best_bets: [] }] });
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    expect(screen.getByText("no bet reported")).toBeInTheDocument();
    expect(screen.queryByText("decision unavailable")).toBeNull();
    expect(screen.queryByText(/below floor/i)).toBeNull();
  });

  it("ignores a cancelled older response after a newer decision arrives", async () => {
    let finishOld!: (value: unknown) => void;
    bestbets.mockImplementation(async (sport: string) => sport === "mlb"
      ? new Promise((resolve) => { finishOld = resolve; })
      : { status: "ok", games: [] });
    await act(async () => { render(<SlateCards />); });
    expect(screen.getByText("decision unavailable")).toBeInTheDocument();

    bestbets.mockResolvedValue({ status: "ok", games: [selected] });
    await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
    expect(screen.getByLabelText("best bet: tier B, 1.00 units")).toBeInTheDocument();
    await act(async () => { finishOld({ status: "unavailable", reason: "request aborted" }); });
    expect(screen.getByLabelText("best bet: tier B, 1.00 units")).toBeInTheDocument();
    expect(screen.queryByText("decision unavailable")).toBeNull();
  });
});
