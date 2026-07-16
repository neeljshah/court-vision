// box-score-panel.test.tsx -- acceptance tests for BoxScorePanel.
//
//   (A) Given a boxscore payload, renders team groups + player rows
//       (min/pts/reb/ast), no $ anywhere.
//   (B) No players yet (game not started) -> honest "no live box score" state,
//       never a fabricated row.
//
// useLiveData is intercepted so no network is hit.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/api", () => ({
  api: { boxscore: vi.fn() },
  isUnavailable: (x: unknown) =>
    !!x && typeof x === "object" && (x as { status?: string }).status === "unavailable",
}));

type LiveDataState<T> = {
  data: T | null;
  ageSec: number | null;
  isStale: boolean;
  error: string | null;
  isLoading: boolean;
};

let _liveState: LiveDataState<unknown> = {
  data: null,
  ageSec: null,
  isStale: false,
  error: null,
  isLoading: true,
};

vi.mock("@/lib/useLiveData", () => ({
  useLiveData: () => _liveState,
}));

import { BoxScorePanel } from "../BoxScorePanel";

describe("BoxScorePanel -- player rows", () => {
  it("renders team groups + player stat rows, no $ anywhere", () => {
    _liveState = {
      data: {
        status: "ok",
        sport: "nba",
        game_id: "g1",
        generated_at: null,
        count: 2,
        players: [
          { player: "A Player", team: "HOME", min: 24, pts: 18, reb: 5, ast: 3 },
          { player: "B Player", team: "AWAY", min: 20, pts: 12, reb: 8, ast: 1 },
        ],
      } as never,
      ageSec: 5,
      isStale: false,
      error: null,
      isLoading: false,
    };
    const { container } = render(<BoxScorePanel sport="nba" gameId="g1" />);
    expect(screen.getByText("A Player")).toBeInTheDocument();
    expect(screen.getByText("HOME")).toBeInTheDocument();
    expect(screen.getByText("AWAY")).toBeInTheDocument();
    expect(container.textContent ?? "").not.toMatch(/\$\d/);
  });
});

describe("BoxScorePanel -- honest empty state", () => {
  it("no players yet -> honest unavailable state, not a fabricated row", () => {
    _liveState = {
      data: {
        status: "ok",
        sport: "nba",
        game_id: "g1",
        generated_at: null,
        count: 0,
        players: [],
        honest_note: "game not started",
      } as never,
      ageSec: 5,
      isStale: false,
      error: null,
      isLoading: false,
    };
    render(<BoxScorePanel sport="nba" gameId="g1" />);
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/game not started/i)).toBeInTheDocument();
  });
});
