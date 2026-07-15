/**
 * game-status.test.tsx
 *
 * Vitest tests for the GameStatusChip primitive, deriveGameStatus helper, and
 * isLikelyDone stale-guard (WS6-game-status-chip, review finding FD-07).
 *
 * Acceptance criteria gated here:
 *   [AC1] deriveGameStatus returns LIVE for live.state='in'
 *   [AC2] deriveGameStatus returns DONE for state='post' and state='final'
 *   [AC3] deriveGameStatus returns PREGAME for an upcoming tipoff
 *   [AC4] isLikelyDone returns true for a tipoff > typicalDuration in the past
 *         with absent state
 *   [AC5] GameStatusChip renders the correct label+tone per status
 *   [AC6] GameStatusChip uses NO green pulse for DONE
 *   [AC7] LIVE chip shows amber-tone pulse; DONE chip does NOT
 *   [AC8] ASCII rail -- no non-ASCII characters in rendered output
 *   [AC9] No dollar figures in the DOM
 *   [AC10] a11y -- role=status + aria-label present on all statuses
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  deriveGameStatus,
  isLikelyDone,
  statusLabel,
  type GameStatus,
} from "../gameStatus";
import { GameStatusChip } from "../GameStatusChip";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ONE_HOUR_MS = 60 * 60 * 1000;
const NOW = 1_718_000_000_000; // fixed "now" for deterministic tests

// A tipoff 3 hours ago (well past any game duration).
const OLD_TIPOFF = NOW - 3 * ONE_HOUR_MS;
// A tipoff 30 minutes from now (future).
const FUTURE_TIPOFF = NOW + 30 * 60 * 1000;
// A tipoff 20 minutes ago (game has started but no state string).
const RECENT_TIPOFF = NOW - 20 * 60 * 1000;

// ---------------------------------------------------------------------------
// [AC1-AC3] deriveGameStatus -- pure helper
// ---------------------------------------------------------------------------

describe("deriveGameStatus -- state string classification", () => {
  it("[AC1] returns LIVE for live.state='in'", () => {
    expect(deriveGameStatus("in", undefined, NOW)).toBe("LIVE");
  });

  it("[AC1] returns LIVE for live.state='live'", () => {
    expect(deriveGameStatus("live", undefined, NOW)).toBe("LIVE");
  });

  it("[AC1] returns LIVE for mixed-case 'In'", () => {
    expect(deriveGameStatus("In", undefined, NOW)).toBe("LIVE");
  });

  it("[AC1] returns LIVE for 'inprogress'", () => {
    expect(deriveGameStatus("inprogress", undefined, NOW)).toBe("LIVE");
  });

  it("[AC2] returns DONE for state='post'", () => {
    expect(deriveGameStatus("post", undefined, NOW)).toBe("DONE");
  });

  it("[AC2] returns DONE for state='final'", () => {
    expect(deriveGameStatus("final", undefined, NOW)).toBe("DONE");
  });

  it("[AC2] returns DONE for state='ft' (soccer full-time)", () => {
    expect(deriveGameStatus("ft", undefined, NOW)).toBe("DONE");
  });

  it("[AC2] returns DONE for state='f' (final abbreviation)", () => {
    expect(deriveGameStatus("f", undefined, NOW)).toBe("DONE");
  });

  it("[AC2] returns DONE for state='finished'", () => {
    expect(deriveGameStatus("finished", undefined, NOW)).toBe("DONE");
  });

  it("[AC2] DONE beats an old tipoff -- settled game never reverts to LIVE", () => {
    // Even though the tipoff is in the past, DONE wins.
    expect(deriveGameStatus("final", OLD_TIPOFF, NOW)).toBe("DONE");
  });

  it("[AC3] returns PREGAME when state is absent and tipoff is in the future", () => {
    expect(deriveGameStatus(null, FUTURE_TIPOFF, NOW)).toBe("PREGAME");
  });

  it("[AC3] returns PREGAME when state is 'upcoming'", () => {
    // 'upcoming' is not in DONE_STATES or LIVE_STATES, tipoff is future.
    expect(deriveGameStatus("upcoming", FUTURE_TIPOFF, NOW)).toBe("PREGAME");
  });

  it("[AC3] returns PREGAME when state is absent and no tipoff supplied", () => {
    expect(deriveGameStatus(undefined, undefined, NOW)).toBe("PREGAME");
  });

  it("returns LIVE when state is absent but tipoff is in the past", () => {
    // Game started 20 min ago, state string not yet available.
    expect(deriveGameStatus(null, RECENT_TIPOFF, NOW)).toBe("LIVE");
  });

  it("returns LIVE when scoreboardActive=true and state is absent", () => {
    expect(deriveGameStatus(null, FUTURE_TIPOFF, NOW, true)).toBe("LIVE");
  });

  it("DONE still wins when scoreboardActive=true -- FD-07 gate", () => {
    // A scoreboard might report active during end-of-game processing;
    // DONE must not be overridden by scoreboardActive.
    expect(deriveGameStatus("post", RECENT_TIPOFF, NOW, true)).toBe("DONE");
  });
});

// ---------------------------------------------------------------------------
// [AC4] isLikelyDone -- stale guard
// ---------------------------------------------------------------------------

describe("isLikelyDone -- stale guard", () => {
  it("[AC4] returns true when tipoff is > typicalDuration in the past", () => {
    // 3 hours ago with 130 min typical duration => definitely done.
    expect(isLikelyDone(OLD_TIPOFF, NOW, 130)).toBe(true);
  });

  it("[AC4] returns true when tipoff is exactly at typicalDuration * 1.2", () => {
    const thresholdMs = 130 * 60 * 1000 * 1.2;
    const tipoff = NOW - thresholdMs;
    expect(isLikelyDone(tipoff, NOW, 130)).toBe(true);
  });

  it("returns false when game is within the typical duration + buffer", () => {
    // Tipoff 30 min ago -- game is ongoing.
    const recentTipoff = NOW - 30 * 60 * 1000;
    expect(isLikelyDone(recentTipoff, NOW, 130)).toBe(false);
  });

  it("returns false when tipoff is in the future", () => {
    expect(isLikelyDone(FUTURE_TIPOFF, NOW, 130)).toBe(false);
  });

  it("respects a custom typicalDurationMin (e.g. 110 min for soccer)", () => {
    // 130 min ago -- past soccer duration but this would normally be 'done' for 110 min.
    const tipoff = NOW - 130 * 60 * 1000;
    // 110 * 1.2 = 132 min threshold, so 130 min ago is NOT yet done.
    expect(isLikelyDone(tipoff, NOW, 110)).toBe(false);
    // But 133 min ago is done.
    const doneTipoff = NOW - 133 * 60 * 1000;
    expect(isLikelyDone(doneTipoff, NOW, 110)).toBe(true);
  });

  it("uses Date.now() when nowMs is omitted (smoke test -- no throw)", () => {
    // Should not throw; just verify it returns a boolean.
    const result = isLikelyDone(Date.now() - 3 * ONE_HOUR_MS);
    expect(typeof result).toBe("boolean");
  });
});

// ---------------------------------------------------------------------------
// statusLabel -- pure string helper
// ---------------------------------------------------------------------------

describe("statusLabel", () => {
  it("returns ASCII strings for all statuses", () => {
    const statuses: GameStatus[] = ["LIVE", "PREGAME", "DONE"];
    for (const s of statuses) {
      const label = statusLabel(s);
      expect(label).not.toMatch(/[-￿]/);
    }
  });
});

// ---------------------------------------------------------------------------
// [AC5-AC10] GameStatusChip -- component rendering
// ---------------------------------------------------------------------------

describe("GameStatusChip -- label and tone", () => {
  it("[AC5] renders 'LIVE' label for LIVE status", () => {
    render(<GameStatusChip status="LIVE" />);
    expect(screen.getByText("LIVE")).toBeInTheDocument();
  });

  it("[AC5] renders 'DONE' label for DONE status", () => {
    render(<GameStatusChip status="DONE" />);
    expect(screen.getByText("DONE")).toBeInTheDocument();
  });

  it("[AC5] renders 'PREGAME' label for PREGAME status", () => {
    render(<GameStatusChip status="PREGAME" />);
    expect(screen.getByText("PREGAME")).toBeInTheDocument();
  });

  it("[AC5] LIVE chip carries warning/stale Tailwind class (not success)", () => {
    const { container } = render(<GameStatusChip status="LIVE" />);
    const chip = container.querySelector('[data-game-status="LIVE"]');
    expect(chip).toBeInTheDocument();
    expect(chip?.className).toMatch(/warning|stale/);
    expect(chip?.className).not.toMatch(/success/);
    expect(chip?.className).not.toMatch(/tier-a/);
  });

  it("[AC5] DONE chip carries neutral border/muted class (no warning, no success)", () => {
    const { container } = render(<GameStatusChip status="DONE" />);
    const chip = container.querySelector('[data-game-status="DONE"]');
    expect(chip?.className).toMatch(/border-border|muted-foreground/);
    expect(chip?.className).not.toMatch(/warning|stale/);
    expect(chip?.className).not.toMatch(/success/);
    expect(chip?.className).not.toMatch(/tier-a/);
  });

  it("[AC5] PREGAME chip carries neutral border/muted class (no warning, no success)", () => {
    const { container } = render(<GameStatusChip status="PREGAME" />);
    const chip = container.querySelector('[data-game-status="PREGAME"]');
    expect(chip?.className).toMatch(/border-border|muted-foreground/);
    expect(chip?.className).not.toMatch(/warning|stale/);
    expect(chip?.className).not.toMatch(/success/);
  });

  it("[AC6] DONE chip contains NO green pulse (animate-ping absent)", () => {
    const { container } = render(<GameStatusChip status="DONE" />);
    // The live pulse uses animate-ping; it must not appear for DONE.
    const pulseEl = container.querySelector(".animate-ping");
    expect(pulseEl).toBeNull();
  });

  it("[AC6] PREGAME chip contains NO green pulse (animate-ping absent)", () => {
    const { container } = render(<GameStatusChip status="PREGAME" />);
    const pulseEl = container.querySelector(".animate-ping");
    expect(pulseEl).toBeNull();
  });

  it("[AC7] LIVE chip shows animate-ping pulse element", () => {
    const { container } = render(<GameStatusChip status="LIVE" />);
    const pulseEl = container.querySelector(".animate-ping");
    expect(pulseEl).toBeInTheDocument();
  });

  it("[AC7] LIVE pulse is warning-coloured (bg-warning)", () => {
    const { container } = render(<GameStatusChip status="LIVE" />);
    const pulseEl = container.querySelector(".animate-ping");
    expect(pulseEl?.className).toMatch(/warning/);
  });
});

// ---------------------------------------------------------------------------
// [AC10] a11y -- role=status + aria-label
// ---------------------------------------------------------------------------

describe("GameStatusChip -- a11y", () => {
  it("[AC10] has role=status for LIVE", () => {
    render(<GameStatusChip status="LIVE" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("[AC10] has role=status for DONE", () => {
    render(<GameStatusChip status="DONE" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("[AC10] has role=status for PREGAME", () => {
    render(<GameStatusChip status="PREGAME" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("[AC10] aria-label is 'LIVE' when no period supplied", () => {
    render(<GameStatusChip status="LIVE" />);
    const el = screen.getByRole("status");
    expect(el.getAttribute("aria-label")).toBe("LIVE");
  });

  it("[AC10] aria-label includes period when period is supplied", () => {
    render(<GameStatusChip status="LIVE" period="Q3 8:42" />);
    const el = screen.getByRole("status");
    expect(el.getAttribute("aria-label")).toBe("LIVE Q3 8:42");
  });

  it("[AC10] aria-label is 'DONE' for a completed game (no period shown)", () => {
    render(<GameStatusChip status="DONE" period="FINAL" />);
    const el = screen.getByRole("status");
    // Period is ignored for DONE (settled game, no live context shown).
    expect(el.getAttribute("aria-label")).toBe("DONE");
  });

  it("[AC10] aria-label is 'PREGAME' for upcoming", () => {
    render(<GameStatusChip status="PREGAME" />);
    const el = screen.getByRole("status");
    expect(el.getAttribute("aria-label")).toBe("PREGAME");
  });
});

// ---------------------------------------------------------------------------
// [AC8] ASCII rail
// ---------------------------------------------------------------------------

describe("GameStatusChip -- ASCII rail", () => {
  const statuses: GameStatus[] = ["LIVE", "PREGAME", "DONE"];

  for (const status of statuses) {
    it(`no non-ASCII characters in ${status} chip`, () => {
      const { container } = render(<GameStatusChip status={status} />);
      const text = container.textContent ?? "";
      expect(text).not.toMatch(/[-￿]/);
    });
  }

  it("no non-ASCII characters when period is supplied", () => {
    const { container } = render(
      <GameStatusChip status="LIVE" period="Q3 8:42" />,
    );
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/[-￿]/);
  });
});

// ---------------------------------------------------------------------------
// [AC9] No dollar figures
// ---------------------------------------------------------------------------

describe("GameStatusChip -- no dollar figures", () => {
  const statuses: GameStatus[] = ["LIVE", "PREGAME", "DONE"];

  for (const status of statuses) {
    it(`no $<digit> pattern in ${status} chip DOM`, () => {
      const { container } = render(<GameStatusChip status={status} />);
      expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
    });
  }
});

// ---------------------------------------------------------------------------
// Size variant -- smoke tests
// ---------------------------------------------------------------------------

describe("GameStatusChip -- size variant", () => {
  it("sm (default) renders without error", () => {
    const { container } = render(<GameStatusChip status="LIVE" size="sm" />);
    expect(container.querySelector('[data-game-status="LIVE"]')).toBeInTheDocument();
  });

  it("md renders without error", () => {
    const { container } = render(<GameStatusChip status="DONE" size="md" />);
    expect(container.querySelector('[data-game-status="DONE"]')).toBeInTheDocument();
  });

  it("sm chip has px-1.5 class", () => {
    const { container } = render(<GameStatusChip status="PREGAME" size="sm" />);
    const chip = container.querySelector('[data-game-status="PREGAME"]');
    expect(chip?.className).toMatch(/px-1\.5/);
  });

  it("md chip has px-2 class", () => {
    const { container } = render(<GameStatusChip status="PREGAME" size="md" />);
    const chip = container.querySelector('[data-game-status="PREGAME"]');
    expect(chip?.className).toMatch(/px-2/);
  });
});

// ---------------------------------------------------------------------------
// className passthrough
// ---------------------------------------------------------------------------

describe("GameStatusChip -- className passthrough", () => {
  it("extra className is applied to the chip wrapper", () => {
    const { container } = render(
      <GameStatusChip status="LIVE" className="custom-test-class" />,
    );
    const chip = container.querySelector('[data-game-status="LIVE"]');
    expect(chip?.className).toMatch(/custom-test-class/);
  });
});
