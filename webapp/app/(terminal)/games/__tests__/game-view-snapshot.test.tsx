import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { Report } from "@/lib/api";
import type { StreamMode } from "@/lib/useStream";

const state = vi.hoisted(() => ({
  snapshot: false,
  mode: "sse" as StreamMode,
  report: null as Report | null,
}));

vi.mock("@/lib/fetchHonest", async (original) => ({
  ...(await original<typeof import("@/lib/fetchHonest")>()),
  get isSnapshotMode() { return state.snapshot; },
}));
vi.mock("@/lib/useStream", () => ({
  useStream: () => ({ data: state.report, mode: state.mode, updatedAt: null }),
}));
vi.mock("@/lib/useLiveData", () => ({
  useLiveData: () => ({ data: null, ageSec: null, isStale: false, error: null }),
  useLiveDataUrl: () => ({ data: null, isLoading: true, isStale: false }),
}));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));

vi.mock("@/components/p6/GameReport", () => ({ GameReport: () => null }));
vi.mock("@/components/p6/BestBets", () => ({ BestBets: () => null }));
vi.mock("@/components/p6/BoxScorePanel", () => ({ BoxScorePanel: () => null }));
vi.mock("@/components/p6/ClvScoreboard", () => ({ ClvScoreboard: () => null }));
vi.mock("@/components/games_depth", () => ({
  CoherentPrediction: () => null,
  GameMarketSurface: () => null,
  ValidatedSignalsStrip: () => null,
}));
vi.mock("@/components/live/LiveInGamePanel", () => ({ LiveInGamePanel: () => null }));
vi.mock("../[sport]/[gameId]/InGameNumber", () => ({ InGameNumber: () => null }));

import { GameView } from "../[sport]/[gameId]/GameView";

function report(live: NonNullable<Report["live"]>): Report {
  return {
    status: "ok",
    sport: "nba",
    game_id: "g1",
    pregame: { home: "SAS", away: "NYK", model_probs: {} },
    markets: [],
    live,
  };
}

function header() {
  const element = document.querySelector("header");
  expect(element).not.toBeNull();
  return element as HTMLElement;
}

function headline() {
  const element = header().querySelector("h1");
  expect(element).not.toBeNull();
  return element as HTMLElement;
}

const helper = "Scores reflect the published snapshot. Current game status is unavailable.";

describe("GameView published snapshot header", () => {
  beforeEach(() => {
    state.snapshot = true;
    state.mode = "sse";
    state.report = report({ status: "Final", away_score: 0, home_score: 0 });
  });

  it.each(["sse", "poll", "disconnected", "idle"] as StreamMode[])(
    "shows the snapshot label instead of the %s connection mode",
    (mode) => {
      state.mode = mode;
      render(<GameView sport="nba" gameId="g1" />);
      const h = header();
      expect(within(h).getByText(/^published snapshot$/i)).toBeInTheDocument();
      expect(within(h).queryByText(/^sse$|^poll$|^live feed unavailable$|^\.\.\.$/i)).toBeNull();
      expect(within(h).getByText(helper)).toBeInTheDocument();
    },
  );

  it("labels saved scores and preserves a source 0-0", () => {
    render(<GameView sport="nba" gameId="g1" />);
    expect(headline().textContent).toMatch(/snapshot score\s*0\s*-\s*0/i);
  });

  it.each(["away_score", "home_score"] as const)(
    "omits the score when %s is missing",
    (missing) => {
      state.report = report({ status: "Final", away_score: 0, home_score: 0 });
      delete state.report.live?.[missing];
      render(<GameView sport="nba" gameId="g1" />);
      expect(headline().textContent).not.toMatch(/snapshot score|\b0\s*-\s*0\b/i);
    },
  );

  it.each([
    { status: "in_progress", period: 3, clock: "4:22" },
    { status: "Final" },
  ])("suppresses archived $status phase badges", (live) => {
    state.report = report({ ...live, away_score: 88, home_score: 92 });
    render(<GameView sport="nba" gameId="g1" />);
    expect(within(header()).queryByText(/^Q3(?:\s|$)|^live$|^final$/i)).toBeNull();
  });
});

describe("GameView ordinary header", () => {
  beforeEach(() => {
    state.snapshot = false;
    state.mode = "sse";
    state.report = report({ status: "Final", away_score: 0, home_score: 0 });
  });

  it.each(["sse", "poll"] as StreamMode[])("keeps %s mode and source scores without snapshot framing", (mode) => {
    state.mode = mode;
    render(<GameView sport="nba" gameId="g1" />);
    const h = header();
    expect(within(h).getByText(mode.toUpperCase(), { exact: true })).toBeInTheDocument();
    expect(headline().textContent).toMatch(/0\s*-\s*0/);
    expect(within(h).getByText(/^final$/i)).toBeInTheDocument();
    expect(within(h).queryByText(/^published snapshot$|^snapshot score$/i)).toBeNull();
    expect(within(h).queryByText(helper)).toBeNull();
  });
});
