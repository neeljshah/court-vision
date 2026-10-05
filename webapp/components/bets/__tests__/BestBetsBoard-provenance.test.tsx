import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { BestBetsBoard as BoardType } from "@/lib/p5api";
import mlbSnapshot from "@/public/demo-data/api_bestbets_board_sport_mlb.json";
import soccerSnapshot from "@/public/demo-data/api_bestbets_board_sport_soccer.json";

const mode = vi.hoisted(() => ({ snapshot: false }));
const refresh = vi.hoisted(() => vi.fn());
const liveState = vi.hoisted(() => ({
  data: null as unknown,
  lastUpdatedAt: null as number | null,
  ageSec: 4 as number | null,
  isStale: false,
  error: null,
  isLoading: false,
  refresh,
}));

vi.mock("@/lib/fetchHonest", () => ({
  get isSnapshotMode() { return mode.snapshot; },
}));
vi.mock("@/lib/useLiveData", () => ({ useLiveData: () => liveState }));
vi.mock("next/navigation", () => ({ useParams: () => ({ sport: "mlb" }) }));
vi.mock("@/lib/p5api", () => ({
  SPORTS: ["mlb", "soccer"],
  isUnavailable: (value: unknown) =>
    !!value && typeof value === "object" && (value as { status?: string }).status === "unavailable",
}));

import { BestBetsBoard } from "../BestBetsBoard";
import SportBetsPageClient from "../../../app/(terminal)/bets/[sport]/SportBetsPageClient";

type BoardWithUnknownTime = Omit<BoardType, "generated_at"> & { generated_at?: unknown };

function fixtureBoard(fixture: unknown, generatedAt?: unknown): BoardWithUnknownTime {
  const board = fixture as BoardType;
  return {
    ...board,
    cards: [], // Preserve the published envelope while keeping this test about provenance.
    count: 0,
    generated_at: generatedAt === undefined ? board.generated_at : generatedAt,
  };
}

function showBoards(boards: Record<string, BoardWithUnknownTime>) {
  liveState.data = {
    boards: Object.fromEntries(Object.entries(boards).map(([sport, board]) => [
      sport, { board, skipped: [] },
    ])),
    unavailableReasons: {},
  };
  render(<BestBetsBoard />);
  return screen.getByTestId("board-observation");
}

describe("BestBetsBoard timestamp provenance", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-05T12:00:00Z"));
    mode.snapshot = false;
    refresh.mockClear();
    liveState.data = null;
    liveState.lastUpdatedAt = Date.now();
    liveState.ageSec = 4;
    liveState.isLoading = false;
  });
  afterEach(() => vi.useRealTimers());

  it("renders the actual published Unix-second board time as a full UTC date", () => {
    mode.snapshot = true;
    const observation = showBoards({ mlb: fixtureBoard(mlbSnapshot) });

    expect(observation).toHaveTextContent("2026-07-16 01:40:25 UTC");
    expect(screen.getByTestId("age-badge").getAttribute("title"))
      .toContain("2026-07-16T01:40:25.608Z");
    expect(screen.getByText("Snapshot data; no scheduled refresh")).toBeInTheDocument();
    expect(screen.queryByTestId("live-pulse")).not.toBeInTheDocument();
    expect(screen.queryByTestId("auto-refresh-label")).not.toBeInTheDocument();
    expect(screen.queryByTestId("next-refresh-countdown")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reload published snapshot" }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("never substitutes the recent page fetch time for missing observation time", () => {
    const observation = showBoards({ mlb: fixtureBoard(mlbSnapshot, null) });

    expect(observation).toHaveTextContent("Board timestamp unavailable");
    expect(screen.queryByTestId("age-badge")).not.toBeInTheDocument();
    expect(observation).not.toHaveTextContent("2026-10-05");
  });

  it("shows oldest and newest board dates and bases age on the oldest", () => {
    const observation = showBoards({
      mlb: fixtureBoard(mlbSnapshot),
      soccer: fixtureBoard(soccerSnapshot, "2026-07-17T03:00:00+02:00"),
    });

    expect(observation).toHaveTextContent("oldest known 2026-07-16 01:40:25 UTC");
    expect(observation).toHaveTextContent("newest known 2026-07-17 01:00:00 UTC");
    expect(screen.getByTestId("age-badge").getAttribute("title"))
      .toContain("2026-07-16T01:40:25.608Z");
  });

  it("counts received boards whose timestamps are missing or invalid", () => {
    const observation = showBoards({
      mlb: fixtureBoard(mlbSnapshot),
      soccer: fixtureBoard(soccerSnapshot, "2026-07-17T01:00:00"),
    });
    expect(observation).toHaveTextContent("1 board timestamp unavailable");
    expect(observation).toHaveTextContent("Known board timestamp: 2026-07-16 01:40:25 UTC");
    expect(screen.queryByTestId("age-badge")).not.toBeInTheDocument();
  });

  it.each(["not-a-date", {}, Infinity])("rejects invalid generated_at %s", (value) => {
    const observation = showBoards({ mlb: fixtureBoard(mlbSnapshot, value) });
    expect(observation).toHaveTextContent("Board timestamp unavailable");
    expect(screen.queryByTestId("age-badge")).not.toBeInTheDocument();
  });

  it("keeps live polling controls and labels fetch age as fetch age", () => {
    showBoards({ mlb: fixtureBoard(mlbSnapshot) });

    expect(screen.getByTestId("live-pulse")).toHaveTextContent("updated 4s ago");
    expect(screen.getByTestId("live-pulse")).toHaveAttribute(
      "title", "Time since last successful fetch; not data age",
    );
    expect(screen.getByTestId("auto-refresh-label")).toHaveTextContent("auto-refreshing every ~30s");
    expect(screen.getByTestId("next-refresh-countdown")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh best bets now" }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("shows the published timestamp on the MLB sport page", () => {
    liveState.data = fixtureBoard(mlbSnapshot);
    render(<SportBetsPageClient />);

    expect(screen.getByTestId("board-observation"))
      .toHaveTextContent("2026-07-16 01:40:25 UTC");
    expect(screen.getByTestId("sport-age-badge").getAttribute("title"))
      .toContain("2026-07-16T01:40:25.608Z");
  });
});
