// GameStatusChip.test.tsx -- FD-07 accept criteria
// liveState="in_progress" -> "LIVE"; past tipoff -> "DONE"; future tipoff -> "PREGAME"
// stale-never-green: LIVE only on explicit liveState, never from tipoff alone.
// No $ in any rendered output.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { GameStatusChip } from "../GameStatusChip";

// Pin "now" so tipoff comparisons are deterministic.
const NOW = new Date("2026-06-20T12:00:00Z").getTime();
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.useRealTimers();
});

const PAST = "2026-06-14T00:30:00Z";   // 6 days ago
const FUTURE = "2026-06-21T19:00:00Z"; // tomorrow

describe("GameStatusChip -- FD-07 accept criteria", () => {
  it('liveState="in_progress" renders LIVE text', () => {
    render(<GameStatusChip tipoff={FUTURE} liveState="in_progress" />);
    expect(screen.getByText("LIVE")).toBeInTheDocument();
  });

  it('liveState="live" (alt form) renders LIVE text', () => {
    render(<GameStatusChip tipoff={FUTURE} liveState="live" />);
    expect(screen.getByText("LIVE")).toBeInTheDocument();
  });

  it("past tipoff with no liveState renders DONE", () => {
    render(<GameStatusChip tipoff={PAST} />);
    expect(screen.getByText("DONE")).toBeInTheDocument();
  });

  it("future tipoff renders PREGAME", () => {
    render(<GameStatusChip tipoff={FUTURE} />);
    expect(screen.getByText("PREGAME")).toBeInTheDocument();
  });

  it("null tipoff (unknown schedule) renders PREGAME not DONE", () => {
    render(<GameStatusChip tipoff={null} />);
    expect(screen.getByText("PREGAME")).toBeInTheDocument();
  });

  it("past tipoff with liveState=post renders DONE (not LIVE)", () => {
    // 'post' is not in_progress/live -> falls through to past-tipoff -> DONE
    render(<GameStatusChip tipoff={PAST} liveState="post" />);
    expect(screen.getByText("DONE")).toBeInTheDocument();
    expect(screen.queryByText("LIVE")).toBeNull();
  });

  it("stale-never-green: past tipoff alone never emits LIVE", () => {
    render(<GameStatusChip tipoff={PAST} />);
    expect(screen.queryByText("LIVE")).toBeNull();
  });

  it("no $ in any rendered output", () => {
    const { container } = render(
      <GameStatusChip tipoff={FUTURE} liveState="in_progress" />,
    );
    expect(container.textContent).not.toMatch(/\$\s*\d/);
  });
});
