/**
 * live-badge.test.tsx -- WS2 acceptance tests for LiveBadge + UpdatedAge.
 *
 * Acceptance criteria verified:
 *   1. Green pulse + "updated" ONLY when isStale=false && !error.
 *   2. Amber "stale" (no green pulse) when isStale=true.
 *   3. Neutral "checking..." when isLoading && ageSec===null.
 *   4. Neutral "unavailable" (NOT red "failed") when error && ageSec===null.
 *   5. Age humanizes correctly: s / m / h suffixes.
 * Additional: ASCII-only; no dollar figures; stale-never-green matrix; a11y.
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LiveBadge } from "../LiveBadge";
import { UpdatedAge, humanizeAge } from "../UpdatedAge";

// Shared prop fixtures
const LIVE = { ageSec: 5, isStale: false, error: null, isLoading: false };
const STALE = { ageSec: 90, isStale: true, error: null, isLoading: false };
const LOADING = { ageSec: null, isStale: false, error: null, isLoading: true };
const ERROR_NO_DATA = { ageSec: null, isStale: false, error: new Error("timeout"), isLoading: false };
const ERROR_WITH_DATA = { ageSec: 120, isStale: false, error: new Error("err"), isLoading: false };
const ALL = [LIVE, STALE, LOADING, ERROR_NO_DATA];

const badge = (c: HTMLElement) => c.querySelector('[role="status"]')!;

// ---------------------------------------------------------------------------
// Criterion 1 -- green live pulse + "updated" ONLY when live
// ---------------------------------------------------------------------------
describe("Criterion 1 -- live state (isStale=false, no error)", () => {
  it("renders 'updated' text in live state", () => {
    render(<LiveBadge {...LIVE} />);
    expect(screen.getByText(/updated/i)).toBeInTheDocument();
  });

  it("wrapper carries a success class in live state", () => {
    const { container } = render(<LiveBadge {...LIVE} />);
    expect(badge(container).className).toMatch(/success/);
  });

  it("renders animate-ping (live pulse dot) in live state", () => {
    const { container } = render(<LiveBadge {...LIVE} />);
    expect(container.querySelector(".animate-ping")).not.toBeNull();
  });

  it("NEGATIVE: no green pulse when isStale=true", () => {
    const { container } = render(<LiveBadge {...STALE} />);
    expect(container.querySelector(".animate-ping")).toBeNull();
  });

  it("NEGATIVE: no green pulse when error", () => {
    const { container } = render(<LiveBadge {...ERROR_NO_DATA} />);
    expect(container.querySelector(".animate-ping")).toBeNull();
  });

  it("does not render 'stale', 'checking', or 'unavailable' in live state", () => {
    render(<LiveBadge {...LIVE} />);
    expect(screen.queryByText(/stale|checking|unavailable/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Criterion 2 -- amber stale, no green pulse
// ---------------------------------------------------------------------------
describe("Criterion 2 -- stale state", () => {
  it("renders 'stale' text", () => {
    render(<LiveBadge {...STALE} />);
    expect(screen.getByText(/stale/i)).toBeInTheDocument();
  });

  it("wrapper is warning-toned, not success", () => {
    const { container } = render(<LiveBadge {...STALE} />);
    expect(badge(container).className).toMatch(/warning/);
    expect(badge(container).className).not.toMatch(/success/);
  });

  it("no animate-ping in stale state", () => {
    const { container } = render(<LiveBadge {...STALE} />);
    expect(container.querySelector(".animate-ping")).toBeNull();
  });

  it("shows age in parentheses (90s -> '1m old')", () => {
    const { container } = render(<LiveBadge {...STALE} />);
    expect(container.textContent).toMatch(/1m old/i);
  });

  it("error with last-good data -> stale warning-toned, no success", () => {
    const { container } = render(<LiveBadge {...ERROR_WITH_DATA} />);
    expect(badge(container).className).toMatch(/warning/);
    expect(badge(container).className).not.toMatch(/success/);
    // 120s -> 2m old
    expect(container.textContent).toMatch(/2m old/i);
  });
});

// ---------------------------------------------------------------------------
// Criterion 3 -- neutral "checking..." state
// ---------------------------------------------------------------------------
describe("Criterion 3 -- checking state (isLoading, no data)", () => {
  it("renders 'checking...' text", () => {
    render(<LiveBadge {...LOADING} />);
    expect(screen.getByText(/checking\.\.\./i)).toBeInTheDocument();
  });

  it("wrapper has no success or warning class", () => {
    const { container } = render(<LiveBadge {...LOADING} />);
    expect(badge(container).className).not.toMatch(/success/);
    expect(badge(container).className).not.toMatch(/warning/);
  });

  it("renders animate-spin (spinner)", () => {
    const { container } = render(<LiveBadge {...LOADING} />);
    expect(container.querySelector(".animate-spin")).not.toBeNull();
  });

  it("suppresses spinner once data arrives (isLoading=true + ageSec!=null)", () => {
    const { container } = render(<LiveBadge ageSec={10} isStale={false} error={null} isLoading={true} />);
    expect(screen.queryByText(/checking/i)).toBeNull();
    expect(container.querySelector(".animate-spin")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Criterion 4 -- neutral "unavailable", NOT red "failed"
// ---------------------------------------------------------------------------
describe("Criterion 4 -- unavailable state (error, no data)", () => {
  it("renders 'unavailable' text", () => {
    render(<LiveBadge {...ERROR_NO_DATA} />);
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
  });

  it("does NOT render 'failed'", () => {
    render(<LiveBadge {...ERROR_NO_DATA} />);
    expect(screen.queryByText(/failed/i)).toBeNull();
  });

  it("wrapper has no red or destructive class (neutral warning)", () => {
    const { container } = render(<LiveBadge {...ERROR_NO_DATA} />);
    expect(badge(container).className).not.toMatch(/\bred\b/);
    expect(badge(container).className).not.toMatch(/destructive/);
    expect(badge(container).className).toMatch(/warning/);
  });

  it("handles string errors without crash", () => {
    render(<LiveBadge ageSec={null} isStale={false} error="timeout" isLoading={false} />);
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Criterion 5 -- humanizeAge s/m/h
// ---------------------------------------------------------------------------
describe("Criterion 5 -- humanizeAge suffixes", () => {
  const cases: [number, string][] = [
    [0, "0s ago"], [1, "1s ago"], [59, "59s ago"],
    [60, "1m ago"], [90, "1m ago"], [3599, "59m ago"],
    [3600, "1h ago"], [7261, "2h ago"],
  ];

  cases.forEach(([sec, expected]) => {
    it(`${sec}s -> "${expected}"`, () => {
      expect(humanizeAge(sec)).toBe(expected);
    });
  });

  it("negative values clamp to 0 (no crash)", () => {
    expect(humanizeAge(-5)).toBe("0s ago");
  });

  it("output is ASCII-only for all cases", () => {
    cases.forEach(([sec]) => {
      expect(humanizeAge(sec)).not.toMatch(/[^\x00-\x7F]/);
    });
  });

  it("live state shows '5s ago' (ageSec=5)", () => {
    const { container } = render(<LiveBadge {...LIVE} />);
    expect(container.textContent).toMatch(/5s ago/);
  });

  it("live state shows '2m ago' (ageSec=130)", () => {
    const { container } = render(<LiveBadge ageSec={130} isStale={false} error={null} />);
    expect(container.textContent).toMatch(/2m ago/);
  });

  it("UpdatedAge renders nothing when ageSec=null", () => {
    const { container } = render(<UpdatedAge ageSec={null} />);
    expect(container.textContent).toBe("");
  });
});

// ---------------------------------------------------------------------------
// a11y -- role, aria-live, aria-atomic in every state
// ---------------------------------------------------------------------------
describe("LiveBadge -- a11y", () => {
  it("has role=status, aria-live=polite, aria-atomic=true in all states", () => {
    ALL.forEach((props) => {
      const { container, unmount } = render(<LiveBadge {...props} />);
      const el = badge(container);
      expect(el.getAttribute("role")).toBe("status");
      expect(el.getAttribute("aria-live")).toBe("polite");
      expect(el.getAttribute("aria-atomic")).toBe("true");
      unmount();
    });
  });

  it("aria-label mentions 'live' or 'updated' in live state", () => {
    const { container } = render(<LiveBadge {...LIVE} />);
    expect(badge(container).getAttribute("aria-label")?.toLowerCase()).toMatch(/live|updated/);
  });

  it("aria-label mentions 'stale' in stale state", () => {
    const { container } = render(<LiveBadge {...STALE} />);
    expect(badge(container).getAttribute("aria-label")?.toLowerCase()).toMatch(/stale/);
  });

  it("aria-label mentions 'checking' in loading state", () => {
    const { container } = render(<LiveBadge {...LOADING} />);
    expect(badge(container).getAttribute("aria-label")?.toLowerCase()).toMatch(/checking/);
  });

  it("aria-label mentions 'unavailable' in error state", () => {
    const { container } = render(<LiveBadge {...ERROR_NO_DATA} />);
    expect(badge(container).getAttribute("aria-label")?.toLowerCase()).toMatch(/unavailable/);
  });
});

// ---------------------------------------------------------------------------
// ASCII rail + no dollar figures
// ---------------------------------------------------------------------------
describe("LiveBadge -- ASCII + no-dollar rails", () => {
  it("emits no non-ASCII in any state", () => {
    ALL.forEach((props) => {
      const { container, unmount } = render(<LiveBadge {...props} />);
      expect(container.textContent ?? "").not.toMatch(/[^\x00-\x7F]/);
      unmount();
    });
  });

  it("no dollar-adjacent digit in any state", () => {
    ALL.forEach((props) => {
      const { container, unmount } = render(<LiveBadge {...props} />);
      expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
      unmount();
    });
  });
});

// ---------------------------------------------------------------------------
// Stale-never-green invariant matrix
// ---------------------------------------------------------------------------
describe("LiveBadge -- stale-never-green invariant", () => {
  const nonLiveStates = [
    { label: "isStale=true", props: STALE },
    { label: "error+data", props: ERROR_WITH_DATA },
    { label: "error+no data", props: ERROR_NO_DATA },
    { label: "loading", props: LOADING },
  ];

  nonLiveStates.forEach(({ label, props }) => {
    it(`no success class when ${label}`, () => {
      const { container } = render(<LiveBadge {...props} />);
      expect(badge(container).className).not.toMatch(/success/);
    });
  });

  it("success class present ONLY in the live state", () => {
    const { container } = render(<LiveBadge {...LIVE} />);
    expect(badge(container).className).toMatch(/success/);
  });
});
