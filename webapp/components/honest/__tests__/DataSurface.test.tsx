// DataSurface.test.tsx -- acceptance suite for the DataSurface robustness wrapper.
//
// Acceptance criteria (all must pass):
//   (a) isLoading -> skeleton: aria-busy present, no error panel, no children
//   (b) error + no data -> neutral unavailable + retry button calls refresh
//   (c) last-good + stale -> renders children + stale badge (not green, not hidden)
//   (d) empty state -> emptySlot or DefaultEmpty rendered (not children)
//   (e) never throws on null/error/loading combinations

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { DataSurface } from "../DataSurface";
import type { LiveDataState } from "@/lib/useLiveData";

// ---------------------------------------------------------------------------
// Helpers: build LiveDataState fixtures
// ---------------------------------------------------------------------------

function loadingState(): LiveDataState<unknown> {
  return {
    data: null,
    lastUpdatedAt: null,
    ageSec: null,
    isStale: false,
    error: null,
    isLoading: true,
    consecutiveFailures: 0,
    backoffActive: false,
    refresh: vi.fn(),
  };
}

function errorNoDataState(msg = "HTTP 503"): LiveDataState<unknown> {
  return {
    data: null,
    lastUpdatedAt: null,
    ageSec: null,
    isStale: true,
    error: msg,
    isLoading: false,
    consecutiveFailures: 1,
    backoffActive: true,
    refresh: vi.fn(),
  };
}

function goodState<T>(data: T, ageSec = 5): LiveDataState<T> {
  return {
    data,
    lastUpdatedAt: Date.now() - ageSec * 1000,
    ageSec,
    isStale: false,
    error: null,
    isLoading: false,
    consecutiveFailures: 0,
    backoffActive: false,
    refresh: vi.fn(),
  };
}

function staleState<T>(data: T, ageSec = 120): LiveDataState<T> {
  return {
    data,
    lastUpdatedAt: Date.now() - ageSec * 1000,
    ageSec,
    isStale: true,
    error: "poll failed",
    isLoading: false,
    consecutiveFailures: 1,
    backoffActive: true,
    refresh: vi.fn(),
  };
}

// ---------------------------------------------------------------------------
// (a) isLoading -> skeleton: aria-busy, no error, no children
// ---------------------------------------------------------------------------

describe("DataSurface (a) -- loading state shows skeleton", () => {
  it("renders with aria-busy=true while loading", () => {
    const { container } = render(
      <DataSurface live={loadingState() as LiveDataState<{ x: number }>}>
        {(d) => <span data-testid="child">{d.x}</span>}
      </DataSurface>,
    );
    const wrapper = container.querySelector("[data-surface-state='loading']");
    expect(wrapper).not.toBeNull();
    expect(wrapper!.getAttribute("aria-busy")).toBe("true");
  });

  it("does NOT render children or an error panel while loading", () => {
    render(
      <DataSurface live={loadingState() as LiveDataState<{ x: number }>}>
        {(d) => <span data-testid="child">{d.x}</span>}
      </DataSurface>,
    );
    expect(screen.queryByTestId("child")).toBeNull();
    // error panel carries data-honest-state="unavailable"
    expect(document.querySelector('[data-honest-state="unavailable"]')).toBeNull();
  });

  it("renders a custom loadingSlot instead of the default skeleton", () => {
    render(
      <DataSurface
        live={loadingState() as LiveDataState<{ x: number }>}
        loadingSlot={<div data-testid="custom-skeleton">loading...</div>}
      >
        {(d) => <span>{d.x}</span>}
      </DataSurface>,
    );
    expect(screen.getByTestId("custom-skeleton")).toBeInTheDocument();
  });

  it("loading label is applied to the aria-label on the wrapper", () => {
    render(
      <DataSurface
        live={loadingState() as LiveDataState<{ x: number }>}
        loadingLabel="Fetching games"
      >
        {(d) => <span>{d.x}</span>}
      </DataSurface>,
    );
    expect(screen.getByLabelText("Fetching games")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// (b) error + no data -> neutral unavailable + retry
// ---------------------------------------------------------------------------

describe("DataSurface (b) -- error without data shows neutral unavailable + retry", () => {
  it("renders the unavailable panel with the error message", () => {
    render(
      <DataSurface live={errorNoDataState("endpoint down") as LiveDataState<{ x: number }>}>
        {(d) => <span>{d.x}</span>}
      </DataSurface>,
    );
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
    expect(screen.getByText("endpoint down")).toBeInTheDocument();
  });

  it("shows a retry button that calls onRetry when clicked", () => {
    const onRetry = vi.fn();
    render(
      <DataSurface
        live={errorNoDataState("down") as LiveDataState<{ x: number }>}
        onRetry={onRetry}
      >
        {(d) => <span>{d.x}</span>}
      </DataSurface>,
    );
    const btn = screen.getByRole("button", { name: /retry/i });
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("does NOT show a retry button when onRetry is omitted", () => {
    render(
      <DataSurface live={errorNoDataState() as LiveDataState<{ x: number }>}>
        {(d) => <span>{d.x}</span>}
      </DataSurface>,
    );
    expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
  });

  it("never renders a red tone class (neutral amber only)", () => {
    const { container } = render(
      <DataSurface live={errorNoDataState() as LiveDataState<{ x: number }>}>
        {(d) => <span>{d.x}</span>}
      </DataSurface>,
    );
    const html = container.innerHTML;
    expect(html).not.toContain("bg-red");
    expect(html).not.toContain("text-red-");
    expect(html).not.toContain("border-red-");
  });

  it("carries data-honest-state=unavailable on the panel", () => {
    const { container } = render(
      <DataSurface live={errorNoDataState() as LiveDataState<{ x: number }>}>
        {(d) => <span>{d.x}</span>}
      </DataSurface>,
    );
    expect(container.querySelector('[data-honest-state="unavailable"]')).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// (c) last-good + stale -> children rendered + stale badge (not green, not hidden)
// ---------------------------------------------------------------------------

describe("DataSurface (c) -- stale: renders children + stale badge (never green)", () => {
  it("renders children when data is present and stale", () => {
    render(
      <DataSurface live={staleState({ score: 99 })}>
        {(d) => <span data-testid="child-score">{d.score}</span>}
      </DataSurface>,
    );
    expect(screen.getByTestId("child-score")).toBeInTheDocument();
    expect(screen.getByText("99")).toBeInTheDocument();
  });

  it("shows the stale badge when isStale=true", () => {
    const { container } = render(
      <DataSurface live={staleState({ score: 1 })}>
        {(d) => <span>{d.score}</span>}
      </DataSurface>,
    );
    const staleBadge = container.querySelector('[data-honest-state="stale"]');
    expect(staleBadge).not.toBeNull();
    expect(staleBadge!.textContent).toMatch(/stale/i);
  });

  it("stale badge is never green (stale-never-green rail)", () => {
    const { container } = render(
      <DataSurface live={staleState({ score: 1 })}>
        {(d) => <span>{d.score}</span>}
      </DataSurface>,
    );
    const html = container.innerHTML;
    expect(html).not.toContain("bg-green");
    expect(html).not.toContain("text-green-");
    expect(html).not.toContain("tier-a");
    expect(html).not.toContain("bg-success");
  });

  it("stale badge includes age when ageSec is provided", () => {
    const { container } = render(
      <DataSurface live={staleState({ score: 1 }, 90)}>
        {(d) => <span>{d.score}</span>}
      </DataSurface>,
    );
    const staleBadge = container.querySelector('[data-honest-state="stale"]');
    expect(staleBadge!.textContent).toMatch(/1m/);
  });

  it("does NOT show the unavailable panel when data is present (even with error)", () => {
    const { container } = render(
      <DataSurface live={staleState({ score: 1 })}>
        {(d) => <span>{d.score}</span>}
      </DataSurface>,
    );
    expect(container.querySelector('[data-honest-state="unavailable"]')).toBeNull();
  });

  it("surface state attribute is 'stale' when isStale=true", () => {
    const { container } = render(
      <DataSurface live={staleState({ score: 1 })}>
        {(d) => <span>{d.score}</span>}
      </DataSurface>,
    );
    expect(container.querySelector("[data-surface-state='stale']")).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// (d) empty state -> emptySlot or DefaultEmpty rendered (not children)
// ---------------------------------------------------------------------------

describe("DataSurface (d) -- empty state renders empty slot (not children)", () => {
  it("renders defaultEmpty when isEmpty returns true and no emptySlot", () => {
    const live = goodState<{ items: number[] }>({ items: [] });
    render(
      <DataSurface live={live} isEmpty={(d) => d.items.length === 0}>
        {(d) => <span data-testid="child">{d.items.join(",")}</span>}
      </DataSurface>,
    );
    // Default empty carries data-honest-state="empty"
    expect(document.querySelector('[data-honest-state="empty"]')).not.toBeNull();
    expect(screen.queryByTestId("child")).toBeNull();
  });

  it("renders a custom emptySlot when provided and isEmpty=true", () => {
    const live = goodState<{ items: number[] }>({ items: [] });
    render(
      <DataSurface
        live={live}
        isEmpty={(d) => d.items.length === 0}
        emptySlot={<div data-testid="custom-empty">No games today.</div>}
      >
        {(d) => <span data-testid="child">{d.items.join(",")}</span>}
      </DataSurface>,
    );
    expect(screen.getByTestId("custom-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("child")).toBeNull();
  });

  it("renders children and NOT empty slot when isEmpty returns false", () => {
    const live = goodState<{ items: number[] }>({ items: [1, 2, 3] });
    render(
      <DataSurface
        live={live}
        isEmpty={(d) => d.items.length === 0}
        emptySlot={<div data-testid="custom-empty">No games.</div>}
      >
        {(d) => <span data-testid="child">{d.items.join(",")}</span>}
      </DataSurface>,
    );
    expect(screen.getByTestId("child")).toBeInTheDocument();
    expect(screen.queryByTestId("custom-empty")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// (e) never throws on null/error/loading combinations
// ---------------------------------------------------------------------------

describe("DataSurface (e) -- never throws on any null/error/loading combination", () => {
  it("renders without throwing when isLoading and data=null", () => {
    expect(() =>
      render(
        <DataSurface live={loadingState() as LiveDataState<{ x: number }>}>
          {(d) => <span>{d.x}</span>}
        </DataSurface>,
      ),
    ).not.toThrow();
  });

  it("renders without throwing when error set and data=null", () => {
    expect(() =>
      render(
        <DataSurface live={errorNoDataState() as LiveDataState<{ x: number }>}>
          {(d) => <span>{d.x}</span>}
        </DataSurface>,
      ),
    ).not.toThrow();
  });

  it("renders without throwing when stale with data", () => {
    expect(() =>
      render(
        <DataSurface live={staleState({ x: 1 })}>
          {(d) => <span>{d.x}</span>}
        </DataSurface>,
      ),
    ).not.toThrow();
  });

  it("renders without throwing when data is good (fresh)", () => {
    expect(() =>
      render(
        <DataSurface live={goodState({ x: 42 })}>
          {(d) => <span>{d.x}</span>}
        </DataSurface>,
      ),
    ).not.toThrow();
  });

  it("renders without throwing on all combinations with no props", () => {
    // Extreme: disabled hook (no loading, no data, no error)
    const disabledLike: LiveDataState<{ x: number }> = {
      data: null,
      lastUpdatedAt: null,
      ageSec: null,
      isStale: false,
      error: null,
      isLoading: false,
      consecutiveFailures: 0,
      backoffActive: false,
      refresh: vi.fn(),
    };
    expect(() =>
      render(
        <DataSurface live={disabledLike}>
          {(d) => <span>{d.x}</span>}
        </DataSurface>,
      ),
    ).not.toThrow();
  });

  it("wrapping DataSurface in DataSurface does not crash (composable)", () => {
    const inner = goodState({ val: "inner" });
    const outer = goodState({ nested: true });
    expect(() =>
      render(
        <DataSurface live={outer}>
          {() => (
            <DataSurface live={inner}>
              {(d) => <span>{d.val}</span>}
            </DataSurface>
          )}
        </DataSurface>,
      ),
    ).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Tone invariants (no green on stale or unavailable)
// ---------------------------------------------------------------------------

describe("DataSurface tone invariants -- stale-never-green + no red on unavailable", () => {
  it("unavailable state has no green classes", () => {
    const { container } = render(
      <DataSurface live={errorNoDataState() as LiveDataState<unknown>}>
        {() => null}
      </DataSurface>,
    );
    const html = container.innerHTML;
    expect(html).not.toContain("bg-green");
    expect(html).not.toContain("text-green");
    expect(html).not.toContain("tier-a");
  });

  it("stale state has no green classes", () => {
    const { container } = render(
      <DataSurface live={staleState({ ok: true })}>
        {(d) => <span>{String(d.ok)}</span>}
      </DataSurface>,
    );
    const html = container.innerHTML;
    expect(html).not.toContain("bg-green");
    expect(html).not.toContain("text-green-");
    expect(html).not.toContain("tier-a");
    expect(html).not.toContain("bg-success");
  });

  it("loading state has no green or red classes", () => {
    const { container } = render(
      <DataSurface live={loadingState() as LiveDataState<unknown>}>
        {() => null}
      </DataSurface>,
    );
    const html = container.innerHTML;
    expect(html).not.toContain("bg-green");
    expect(html).not.toContain("text-red-");
    expect(html).not.toContain("bg-red-");
  });
});
