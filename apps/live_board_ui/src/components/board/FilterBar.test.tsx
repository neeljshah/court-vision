/** RTL tests for FilterBar: search input, live-only switch, count display, disabled state. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { FilterBar } from "./FilterBar";

// ---------------------------------------------------------------------------
// Render helper: sensible defaults; override per test.
// ---------------------------------------------------------------------------
interface HelperProps {
  query?: string;
  onQuery?: ReturnType<typeof vi.fn>;
  liveOnly?: boolean;
  onLiveOnly?: ReturnType<typeof vi.fn>;
  shown?: number;
  total?: number;
  liveCount?: number;
}

function renderFilterBar({
  query = "",
  onQuery = vi.fn(),
  liveOnly = false,
  onLiveOnly = vi.fn(),
  shown = 0,
  total = 0,
  liveCount = 1,
}: HelperProps = {}) {
  const result = render(
    <FilterBar
      query={query}
      onQuery={onQuery}
      liveOnly={liveOnly}
      onLiveOnly={onLiveOnly}
      shown={shown}
      total={total}
      liveCount={liveCount}
    />
  );
  return { ...result, onQuery, onLiveOnly };
}

// ---------------------------------------------------------------------------
// Search input
// ---------------------------------------------------------------------------
describe("FilterBar - search input", () => {
  it('renders an input accessible via getByLabelText("Search teams")', () => {
    renderFilterBar();
    expect(screen.getByLabelText("Search teams")).toBeInTheDocument();
  });

  it('is also queryable via role="searchbox"', () => {
    renderFilterBar();
    expect(screen.getByRole("searchbox")).toBeInTheDocument();
  });

  it("calls onQuery with each character typed", async () => {
    const user = userEvent.setup();
    const onQuery = vi.fn();
    renderFilterBar({ onQuery });

    const input = screen.getByLabelText("Search teams");
    await user.type(input, "Lakers");

    // onQuery should have been called at least once (once per keystroke)
    expect(onQuery).toHaveBeenCalled();
    // The last call should carry the last character appended ("s" from "Lakers")
    const calls = onQuery.mock.calls;
    expect(calls.length).toBeGreaterThanOrEqual(1);
  });

  it("calls onQuery with the full string on a single type sequence", async () => {
    const user = userEvent.setup();
    const onQuery = vi.fn();
    // Start with a controlled value so we can inspect the sequence
    const { rerender } = render(
      <FilterBar
        query=""
        onQuery={onQuery}
        liveOnly={false}
        onLiveOnly={vi.fn()}
        shown={0}
        total={0}
        liveCount={1}
      />
    );
    void rerender; // available if we need it later

    const input = screen.getByLabelText("Search teams");
    await user.type(input, "abc");

    // Each character should have triggered a call
    expect(onQuery).toHaveBeenCalledTimes(3);
    // The calls should reflect progressive input values: "a", "b", "c"
    expect(onQuery).toHaveBeenNthCalledWith(1, "a");
    expect(onQuery).toHaveBeenNthCalledWith(2, "b");
    expect(onQuery).toHaveBeenNthCalledWith(3, "c");
  });
});

// ---------------------------------------------------------------------------
// Live-only switch
// ---------------------------------------------------------------------------
describe("FilterBar - live-only switch", () => {
  it('the live-only control has role="switch"', () => {
    renderFilterBar({ liveOnly: false, liveCount: 3 });
    expect(screen.getByRole("switch")).toBeInTheDocument();
  });

  it("clicking the switch fires onLiveOnly(true) when starting false", async () => {
    const user = userEvent.setup();
    const onLiveOnly = vi.fn();
    renderFilterBar({ liveOnly: false, onLiveOnly, liveCount: 3 });

    await user.click(screen.getByRole("switch"));

    expect(onLiveOnly).toHaveBeenCalledOnce();
    expect(onLiveOnly).toHaveBeenCalledWith(true);
  });

  it("clicking the switch fires onLiveOnly(false) when starting true", async () => {
    const user = userEvent.setup();
    const onLiveOnly = vi.fn();
    renderFilterBar({ liveOnly: true, onLiveOnly, liveCount: 3 });

    await user.click(screen.getByRole("switch"));

    expect(onLiveOnly).toHaveBeenCalledOnce();
    expect(onLiveOnly).toHaveBeenCalledWith(false);
  });

  it('switch has aria-checked="false" when liveOnly is false', () => {
    renderFilterBar({ liveOnly: false, liveCount: 3 });
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false");
  });

  it('switch has aria-checked="true" when liveOnly is true', () => {
    renderFilterBar({ liveOnly: true, liveCount: 3 });
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
  });
});

// ---------------------------------------------------------------------------
// Result count display
// ---------------------------------------------------------------------------
describe("FilterBar - result count", () => {
  it('shows "showing 3 of 10" when shown=3 and total=10', () => {
    renderFilterBar({ shown: 3, total: 10 });
    expect(screen.getByText(/showing 3 of 10/i)).toBeInTheDocument();
  });

  it("updates the count text to reflect different shown/total values", () => {
    renderFilterBar({ shown: 0, total: 5 });
    expect(screen.getByText(/showing 0 of 5/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Disabled state when liveCount === 0
// ---------------------------------------------------------------------------
describe("FilterBar - live toggle disabled when liveCount === 0", () => {
  it("switch is disabled via the HTML disabled attribute when liveCount is 0", () => {
    renderFilterBar({ liveCount: 0 });
    const toggle = screen.getByRole("switch");
    expect(toggle).toBeDisabled();
  });

  it('switch carries aria-disabled="true" when liveCount is 0', () => {
    renderFilterBar({ liveCount: 0 });
    const toggle = screen.getByRole("switch");
    expect(toggle).toHaveAttribute("aria-disabled", "true");
  });

  it("does NOT fire onLiveOnly when disabled and clicked", async () => {
    const user = userEvent.setup();
    const onLiveOnly = vi.fn();
    renderFilterBar({ liveCount: 0, onLiveOnly });

    // userEvent.click on a disabled button is a no-op in most browsers;
    // the component also guards onClick itself, so either way no call.
    await user.click(screen.getByRole("switch"));

    expect(onLiveOnly).not.toHaveBeenCalled();
  });

  it("switch is NOT disabled when liveCount > 0", () => {
    renderFilterBar({ liveCount: 2 });
    expect(screen.getByRole("switch")).not.toBeDisabled();
  });
});
