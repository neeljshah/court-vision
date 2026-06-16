/** RTL tests for StampBar: stale indicator, connectionIssue chip, counts, and refresh button. */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { StampBar } from "./StampBar";

// ---------------------------------------------------------------------------
// Render helper: sensible defaults; override per test.
// ---------------------------------------------------------------------------
interface HelperProps {
  generatedAt?: string | null;
  liveCount?: number;
  upcomingCount?: number;
  finishedCount?: number;
  refreshing?: boolean;
  onRefresh?: ReturnType<typeof vi.fn>;
  stale?: boolean;
  connectionIssue?: boolean;
}

function renderStampBar({
  generatedAt = "2026-01-01T12:00:00Z",
  liveCount = 0,
  upcomingCount = 0,
  finishedCount = 0,
  refreshing = false,
  onRefresh = vi.fn(),
  stale,
  connectionIssue,
}: HelperProps = {}) {
  // Only spread optional props when explicitly provided so we can test the
  // omitted-prop (default-false) case separately from the explicit false case.
  const extraProps = {
    ...(stale !== undefined ? { stale } : {}),
    ...(connectionIssue !== undefined ? { connectionIssue } : {}),
  };
  const result = render(
    <StampBar
      generatedAt={generatedAt}
      liveCount={liveCount}
      upcomingCount={upcomingCount}
      finishedCount={finishedCount}
      refreshing={refreshing}
      onRefresh={onRefresh}
      {...extraProps}
    />
  );
  return { ...result, onRefresh };
}

// ---------------------------------------------------------------------------
// Stale indicator absent when stale is false or omitted
// ---------------------------------------------------------------------------
describe("StampBar - no stale indicator when fresh", () => {
  it("does NOT render the delayed indicator when stale prop is omitted", () => {
    renderStampBar();
    expect(screen.queryByText(/delayed/i)).toBeNull();
  });

  it("does NOT render the delayed indicator when stale=false", () => {
    renderStampBar({ stale: false });
    expect(screen.queryByText(/delayed/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Stale indicator present and accessible when stale=true
// ---------------------------------------------------------------------------
describe("StampBar - stale indicator when stale=true", () => {
  it("renders the delayed indicator text", () => {
    renderStampBar({ stale: true });
    expect(screen.getByText(/delayed/i)).toBeInTheDocument();
  });

  it("the delayed element has an accessible label mentioning delayed", () => {
    renderStampBar({ stale: true });
    // The span carries aria-label "Data may be delayed; trying to refresh."
    const pill = screen.getByText(/delayed/i);
    // Check via closest element that has the aria-label, or the element itself.
    const labeled =
      pill.closest("[aria-label]") ?? pill.closest("[title]") ?? pill;
    const ariaLabel =
      labeled.getAttribute("aria-label") ?? labeled.getAttribute("title") ?? "";
    expect(ariaLabel.toLowerCase()).toContain("delayed");
  });

  it("the delayed pill is NOT rendered when stale flips back to false", () => {
    const { rerender } = renderStampBar({ stale: true });
    expect(screen.getByText(/delayed/i)).toBeInTheDocument();

    rerender(
      <StampBar
        generatedAt="2026-01-01T12:00:00Z"
        liveCount={0}
        upcomingCount={0}
        finishedCount={0}
        refreshing={false}
        onRefresh={vi.fn()}
        stale={false}
      />
    );
    expect(screen.queryByText(/delayed/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// connectionIssue chip: priority over the stale "delayed" chip
// ---------------------------------------------------------------------------
describe("StampBar - connectionIssue chip", () => {
  it("renders a reconnecting indicator when connectionIssue=true", () => {
    renderStampBar({ connectionIssue: true });
    expect(screen.getByText(/reconnecting/i)).toBeInTheDocument();
  });

  it("does NOT render the delayed chip when connectionIssue=true, even if stale=true", () => {
    // connectionIssue takes priority; only one chip should appear
    renderStampBar({ connectionIssue: true, stale: true });
    expect(screen.getByText(/reconnecting/i)).toBeInTheDocument();
    expect(screen.queryByText(/delayed/i)).toBeNull();
  });

  it("renders delayed (not reconnecting) when connectionIssue=false and stale=true", () => {
    renderStampBar({ connectionIssue: false, stale: true });
    expect(screen.getByText(/delayed/i)).toBeInTheDocument();
    expect(screen.queryByText(/reconnecting/i)).toBeNull();
  });

  it("renders neither chip when connectionIssue=false and stale=false", () => {
    renderStampBar({ connectionIssue: false, stale: false });
    expect(screen.queryByText(/reconnecting/i)).toBeNull();
    expect(screen.queryByText(/delayed/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Count display
// ---------------------------------------------------------------------------
describe("StampBar - count display", () => {
  it("shows the live count when liveCount > 0", () => {
    renderStampBar({ liveCount: 2, upcomingCount: 3 });
    // The live count renders as a standalone token containing "2"
    expect(screen.getByText(/\b2\b/)).toBeInTheDocument();
  });

  it("shows the upcoming count string when upcomingCount > 0", () => {
    renderStampBar({ liveCount: 2, upcomingCount: 3 });
    // upcomingCount renders as "3 upcoming"
    expect(screen.getByText(/3 upcoming/i)).toBeInTheDocument();
  });

  it("renders liveCount=2 and upcomingCount=3 together", () => {
    const { container } = renderStampBar({ liveCount: 2, upcomingCount: 3 });
    // Both values are present in the rendered output
    expect(container.textContent).toContain("2");
    expect(container.textContent).toContain("3 upcoming");
  });

  it('shows "0 games" when all counts are zero', () => {
    renderStampBar({ liveCount: 0, upcomingCount: 0, finishedCount: 0 });
    expect(screen.getByText(/0 games/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Refresh button
// ---------------------------------------------------------------------------
describe("StampBar - refresh button", () => {
  it('renders the refresh button with aria-label "Refresh now"', () => {
    renderStampBar();
    expect(screen.getByRole("button", { name: /refresh now/i })).toBeInTheDocument();
  });

  it("calls onRefresh when the refresh button is clicked", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    renderStampBar({ onRefresh });

    await user.click(screen.getByRole("button", { name: /refresh now/i }));

    expect(onRefresh).toHaveBeenCalledOnce();
  });

  it("the refresh button is disabled while refreshing=true", () => {
    renderStampBar({ refreshing: true });
    expect(screen.getByRole("button", { name: /refresh now/i })).toBeDisabled();
  });

  it("does NOT call onRefresh when the button is disabled (refreshing=true)", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    renderStampBar({ refreshing: true, onRefresh });

    await user.click(screen.getByRole("button", { name: /refresh now/i }));

    expect(onRefresh).not.toHaveBeenCalled();
  });
});
