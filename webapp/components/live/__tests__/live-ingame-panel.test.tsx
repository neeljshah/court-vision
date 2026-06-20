/**
 * live-ingame-panel.test.tsx -- WS4 acceptance tests for LiveInGamePanel.
 *
 * Acceptance criteria:
 *  1. Renders live score + quarter + win-prob bar for an in_progress game.
 *  2. Shows "Final" (not a live bar) for a post-game.
 *  3. Shows pregame number (calibrated, not edge) for a future/pregame game.
 *  4. Never greens on stale (stale-never-green invariant).
 *  5. Win-prob bar is labeled "CALIBRATION -- not edge" (no $/edge claim).
 *  6. ASCII only; no dollar figures in any state.
 *  7. In-game CLV may be INSUFFICIENT_DATA -- shown honestly.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import type { InGameFull } from "@/lib/types";

// Mock useLiveDataUrl so tests are synchronous and deterministic.
const mockState = {
  data: null as InGameFull | null,
  ageSec: null as number | null,
  isStale: false,
  error: null as string | null,
  isLoading: false,
};

vi.mock("@/lib/useLiveData", () => ({
  useLiveDataUrl: () => ({ ...mockState, lastUpdatedAt: null, refresh: vi.fn() }),
  useLiveData: vi.fn(),
}));

vi.mock("@/lib/p5api", async (orig) => {
  const real = (await orig()) as Record<string, unknown>;
  return { ...real, P5_BASE: "http://localhost:8099" };
});

import { LiveInGamePanel } from "../LiveInGamePanel";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const IN_PROGRESS: InGameFull = {
  status: "ok", sport: "nba", game_id: "g1", generated_at: null,
  score: { home: 88, away: 82, period: 3, clock: "7:42" },
  win_prob: { p_home: 0.64, provenance: ["base sigmoid", "platt"], model: "nba_v2" },
  clv_status: "INSUFFICIENT_DATA", edge_claimed: false,
};

const POST_GAME: InGameFull = {
  status: "ok", sport: "nba", game_id: "g2", generated_at: null,
  score: { home: 115, away: 108, period: 4, clock: "0:00" },
  win_prob: null, clv_status: null, edge_claimed: false,
};

const PREGAME: InGameFull = {
  status: "ok", sport: "nba", game_id: "g3", generated_at: null,
  score: { home: null, away: null, period: null, clock: null },
  win_prob: null, clv_status: null, edge_claimed: false,
};

const MATCHUP = "NYK @ SAS";
const BASE_PROPS = { sport: "nba", gameId: "g1", matchupLabel: MATCHUP } as const;

function assertNoDollar(c: HTMLElement) {
  expect(c.textContent ?? "").not.toMatch(/\$\s*\d/);
}
function assertAsciiOnly(c: HTMLElement) {
  expect(c.textContent ?? "").not.toMatch(/[^\x00-\x7F]/);
}
function setLive(overrides: Partial<typeof mockState>) {
  Object.assign(mockState, {
    data: null, ageSec: null, isStale: false, error: null, isLoading: false,
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Criterion 1 -- in_progress: score + quarter/clock + win-prob bar
// ---------------------------------------------------------------------------

describe("Criterion 1 -- in_progress renders score + quarter + win-prob bar", () => {
  beforeEach(() => setLive({ data: IN_PROGRESS, ageSec: 5 }));

  it("renders the in-progress state container", () => {
    render(<LiveInGamePanel {...BASE_PROPS} />);
    expect(screen.getByTestId("in-progress-state")).toBeInTheDocument();
  });

  it("score line contains home (88) and away (82) scores", () => {
    render(<LiveInGamePanel {...BASE_PROPS} />);
    const sl = screen.getByTestId("score-line").textContent ?? "";
    expect(sl).toMatch(/88/);
    expect(sl).toMatch(/82/);
  });

  it("quarter-clock shows Q3 and 7:42", () => {
    render(<LiveInGamePanel {...BASE_PROPS} />);
    const qc = screen.getByTestId("quarter-clock").textContent ?? "";
    expect(qc).toMatch(/Q3/);
    expect(qc).toMatch(/7:42/);
  });

  it("renders the win-prob bar", () => {
    render(<LiveInGamePanel {...BASE_PROPS} />);
    expect(screen.getByTestId("win-prob-bar")).toBeInTheDocument();
  });

  it("shows home win probability 64%", () => {
    render(<LiveInGamePanel {...BASE_PROPS} />);
    expect(screen.getByText(/64%/)).toBeInTheDocument();
  });

  it("shows CALIBRATION -- not edge label text", () => {
    render(<LiveInGamePanel {...BASE_PROPS} />);
    expect(screen.getByText(/CALIBRATION -- not edge/)).toBeInTheDocument();
  });

  it("no dollar figures", () => {
    const { container } = render(<LiveInGamePanel {...BASE_PROPS} />);
    assertNoDollar(container);
  });

  it("ASCII only", () => {
    const { container } = render(<LiveInGamePanel {...BASE_PROPS} />);
    assertAsciiOnly(container);
  });
});

// ---------------------------------------------------------------------------
// Criterion 2 -- post-game: shows Final, no live win-prob bar
// ---------------------------------------------------------------------------

describe("Criterion 2 -- post-game shows Final, no live win-prob bar", () => {
  beforeEach(() => setLive({ data: POST_GAME, ageSec: 20, gameId: "g2" } as Partial<typeof mockState>));

  it("renders final-state", () => {
    render(<LiveInGamePanel sport="nba" gameId="g2" matchupLabel={MATCHUP} />);
    expect(screen.getByTestId("final-state")).toBeInTheDocument();
  });

  it("shows 'Final' text", () => {
    render(<LiveInGamePanel sport="nba" gameId="g2" matchupLabel={MATCHUP} />);
    expect(screen.getByText(/Final/)).toBeInTheDocument();
  });

  it("does NOT render a win-prob bar for post game", () => {
    render(<LiveInGamePanel sport="nba" gameId="g2" matchupLabel={MATCHUP} />);
    expect(screen.queryByTestId("win-prob-bar")).toBeNull();
  });

  it("does NOT render quarter/clock for post game", () => {
    render(<LiveInGamePanel sport="nba" gameId="g2" matchupLabel={MATCHUP} />);
    expect(screen.queryByTestId("quarter-clock")).toBeNull();
  });

  it("no dollar figures in post state", () => {
    const { container } = render(
      <LiveInGamePanel sport="nba" gameId="g2" matchupLabel={MATCHUP} />,
    );
    assertNoDollar(container);
  });
});

// ---------------------------------------------------------------------------
// Criterion 3 -- pregame: shows pregame number (calibrated, not edge)
// ---------------------------------------------------------------------------

describe("Criterion 3 -- pregame shows calibrated number, not a live bar", () => {
  beforeEach(() => setLive({ data: PREGAME, ageSec: 10 }));

  it("renders pregame-state", () => {
    render(<LiveInGamePanel {...BASE_PROPS} gameId="g3" pregameProb={0.57} />);
    expect(screen.getByTestId("pregame-state")).toBeInTheDocument();
  });

  it("shows the pregame prob 57.0%", () => {
    render(<LiveInGamePanel {...BASE_PROPS} gameId="g3" pregameProb={0.57} />);
    expect(screen.getByText(/57\.0%/)).toBeInTheDocument();
  });

  it("labels it as calibration, not edge", () => {
    render(<LiveInGamePanel {...BASE_PROPS} gameId="g3" pregameProb={0.57} />);
    expect(screen.getByText(/pregame calibration -- not edge/)).toBeInTheDocument();
  });

  it("shows 'no live data yet' when pregameProb is null", () => {
    render(<LiveInGamePanel {...BASE_PROPS} gameId="g3" pregameProb={null} />);
    expect(screen.getByTestId("pregame-no-prob")).toBeInTheDocument();
  });

  it("does NOT show a win-prob bar for pregame", () => {
    render(<LiveInGamePanel {...BASE_PROPS} gameId="g3" pregameProb={0.57} />);
    expect(screen.queryByTestId("win-prob-bar")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Criterion 4 -- stale-never-green invariant
// ---------------------------------------------------------------------------

describe("Criterion 4 -- stale-never-green invariant", () => {
  const staleStates: Array<{ label: string; overrides: Partial<typeof mockState> }> = [
    { label: "isStale=true", overrides: { data: IN_PROGRESS, ageSec: 200, isStale: true } },
    { label: "error+no data", overrides: { data: null, ageSec: null, error: "timeout" } },
    { label: "loading+no data", overrides: { data: null, ageSec: null, isLoading: true } },
  ];

  staleStates.forEach(({ label, overrides }) => {
    it(`no green class on LiveBadge role=status when ${label}`, () => {
      setLive(overrides);
      const { container } = render(<LiveInGamePanel {...BASE_PROPS} />);
      const badge = container.querySelector('[role="status"]');
      expect(badge?.className ?? "").not.toMatch(/green/);
    });
  });
});

// ---------------------------------------------------------------------------
// Criterion 5 -- win-prob bar labeled CALIBRATION, no edge claim
// ---------------------------------------------------------------------------

describe("Criterion 5 -- win-prob bar CALIBRATION label, no edge claim", () => {
  beforeEach(() => setLive({ data: IN_PROGRESS, ageSec: 5 }));

  it("win-prob bar aria-label contains 'calibration'", () => {
    render(<LiveInGamePanel {...BASE_PROPS} />);
    const bar = screen.getByTestId("win-prob-bar");
    expect((bar.getAttribute("aria-label") ?? "").toLowerCase()).toMatch(/calibration/);
  });

  it("win-prob bar aria-label does not contain 'edge' or '$'", () => {
    render(<LiveInGamePanel {...BASE_PROPS} />);
    const label = (screen.getByTestId("win-prob-bar").getAttribute("aria-label") ?? "").toLowerCase();
    expect(label).not.toMatch(/\bedge\b/);
    expect(label).not.toMatch(/\$/);
  });
});

// ---------------------------------------------------------------------------
// Criterion 6 -- ASCII only across all states
// ---------------------------------------------------------------------------

describe("Criterion 6 -- ASCII only across all game states", () => {
  it("in_progress state: ASCII only, no $", () => {
    setLive({ data: IN_PROGRESS, ageSec: 5 });
    const { container } = render(<LiveInGamePanel {...BASE_PROPS} pregameProb={0.55} />);
    assertAsciiOnly(container);
    assertNoDollar(container);
  });

  it("post state: ASCII only, no $", () => {
    setLive({ data: POST_GAME, ageSec: 20 });
    const { container } = render(<LiveInGamePanel sport="nba" gameId="g2" matchupLabel={MATCHUP} />);
    assertAsciiOnly(container);
    assertNoDollar(container);
  });

  it("pregame state: ASCII only, no $", () => {
    setLive({ data: PREGAME, ageSec: 10 });
    const { container } = render(<LiveInGamePanel {...BASE_PROPS} gameId="g3" pregameProb={0.55} />);
    assertAsciiOnly(container);
    assertNoDollar(container);
  });

  it("error state: ASCII only, no $", () => {
    setLive({ data: null, ageSec: null, error: "timeout" });
    const { container } = render(<LiveInGamePanel {...BASE_PROPS} />);
    assertAsciiOnly(container);
    assertNoDollar(container);
  });
});

// ---------------------------------------------------------------------------
// Criterion 7 -- CLV INSUFFICIENT_DATA shown honestly
// ---------------------------------------------------------------------------

describe("Criterion 7 -- CLV INSUFFICIENT_DATA shown honestly", () => {
  it("renders INSUFFICIENT_DATA text when clv_status is set", () => {
    setLive({ data: IN_PROGRESS, ageSec: 5 });
    render(<LiveInGamePanel {...BASE_PROPS} />);
    expect(screen.getByText(/INSUFFICIENT_DATA/)).toBeInTheDocument();
  });

  it("includes 'unproven' alongside INSUFFICIENT_DATA (honest framing)", () => {
    setLive({ data: { ...IN_PROGRESS, clv_status: "INSUFFICIENT_DATA" }, ageSec: 5 });
    render(<LiveInGamePanel {...BASE_PROPS} />);
    expect(screen.getByText(/unproven/i)).toBeInTheDocument();
  });

  it("shows no CLV text when clv_status is null (post game)", () => {
    setLive({ data: POST_GAME, ageSec: 20 });
    render(<LiveInGamePanel sport="nba" gameId="g2" matchupLabel={MATCHUP} />);
    // No CLV block should appear in a post-game view
    expect(screen.queryByText(/CLV:/)).toBeNull();
  });
});
