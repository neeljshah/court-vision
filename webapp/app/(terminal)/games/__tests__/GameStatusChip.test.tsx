import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { PredictRecord, GameEdge } from "@/lib/p5api";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

async function load(snapshot = false) {
  vi.stubEnv("NEXT_PUBLIC_DATA_MODE", snapshot ? "snapshot" : "");
  vi.resetModules();
  return import("../GameStatusChip");
}

describe("Game status requires an explicit source phase", () => {
  it.each([
    ["pre", "PREGAME"], ["in", "LIVE"], ["post", "DONE"],
    ["in_progress", "LIVE"], ["live", "LIVE"], [" IN ", "LIVE"],
  ])("renders reported %s as %s", async (state, label) => {
    const { GameStatusChip } = await load();
    render(<GameStatusChip state={state} />);
    expect(screen.getByText(label)).toHaveAttribute(
      "aria-label", `Reported game status: ${label.toLowerCase()}`,
    );
  });

  it.each([undefined, "", "ok", "unavailable", "not_live", "live_ended", "__proto__"])(
    "does not infer a phase from %s", async (state) => {
      const { GameStatusChip } = await load();
      render(<GameStatusChip state={state} />);
      expect(screen.getByText("STATUS UNKNOWN")).toBeInTheDocument();
      expect(screen.queryByText("LIVE")).toBeNull();
    },
  );

  it.each([undefined, "pre", "in", "post", "live", "in_progress"])(
    "labels historical state %s as a neutral snapshot", async (state) => {
      const { GameStatusChip } = await load(true);
      const { container } = render(<GameStatusChip state={state} />);
      expect(screen.getByText("SNAPSHOT")).toHaveAttribute(
        "aria-label", "Published historical snapshot; current game status is not available.",
      );
      expect(screen.queryByText(/^(LIVE|PREGAME|DONE)$/)).toBeNull();
      expect(container.querySelector('[class*="animate-"], [class*="text-up"]')).toBeNull();
    },
  );
});

const record: PredictRecord = {
  sport: "mlb", game_id: "test-game", home: "Home", away: "Away",
  tipoff: null, pregame_probs: {}, markets: [], produced_at: null,
  leak_guard: { in_sample: false },
};

describe("GameCard status source", () => {
  it.each([null, "invalid", "2000-01-01T00:00:00Z", "2999-01-01T00:00:00Z"])(
    "does not infer a phase from tipoff %s or the edge envelope", async (tipoff) => {
      await load();
      const { GameCard } = await import("../GameCard");
      render(<GameCard sport="mlb" rec={{ ...record, tipoff }}
        edge={{ game_id: record.game_id, status: "live" }} />);
      expect(screen.getByText("STATUS UNKNOWN")).toBeInTheDocument();
    },
  );

  it.each([
    ["ok", "in", "LIVE"], ["ok", "pre", "PREGAME"],
    ["ok", "post", "DONE"], ["ok", undefined, "STATUS UNKNOWN"],
    ["unavailable", "in", "STATUS UNKNOWN"],
  ])("uses live.state only with a healthy feed (%s, %s)", async (status, state, label) => {
    await load();
    const { GameCard } = await import("../GameCard");
    const edge: GameEdge = { game_id: record.game_id, status: "ok", live: { status, state } };
    render(<GameCard sport="mlb" rec={record} edge={edge} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
