// PanelErrorBoundary.test.tsx -- acceptance suite for the reusable ErrorBoundary.
//
// Acceptance criteria (all must pass):
//   (a) child that throws during render -> honest fallback shown (not blank, not green)
//   (b) the boundary does NOT rethrow or crash the test runner
//   (c) a healthy child renders unchanged (the boundary is transparent)
//   (d) retry/reset control re-attempts to render children (generation key reset)
//   (e) noRetry prop suppresses the retry button
//   (f) no red or green tone classes ever appear in the error fallback
//   (g) withPanelErrorBoundary convenience wrapper works identically

import { describe, it, expect, vi, beforeAll, afterAll } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { Component, type ReactNode } from "react";
import { PanelErrorBoundary, withPanelErrorBoundary } from "../PanelErrorBoundary";

// ---------------------------------------------------------------------------
// Helpers: components that throw or succeed
// ---------------------------------------------------------------------------

/** A component that always throws on render -- simulates a broken panel. */
function AlwaysThrows({ message = "test error" }: { message?: string }): ReactNode {
  throw new Error(message);
}

/** A component that renders its content normally. */
function HealthyPanel({ text = "healthy content" }: { text?: string }): ReactNode {
  return <div data-testid="healthy-panel">{text}</div>;
}

/**
 * A stateful component that conditionally throws.
 * Useful for testing reset: after reset children should re-render,
 * and if we stop throwing they should render successfully.
 */
interface TogglableProps {
  shouldThrow: boolean;
}

class TogglablePanel extends Component<TogglableProps> {
  override render(): ReactNode {
    if (this.props.shouldThrow) throw new Error("toggled error");
    return <div data-testid="togglable-panel">recovered</div>;
  }
}

// ---------------------------------------------------------------------------
// Suppress expected console.error output from intentional throws in tests.
// We only suppress the specific boundary-logging messages; all other errors
// remain loud. React itself also logs uncaught errors -- suppress that too.
// ---------------------------------------------------------------------------

let originalError: typeof console.error;
beforeAll(() => {
  originalError = console.error;
  console.error = (...args: unknown[]) => {
    const first = String(args[0] ?? "");
    // Suppress expected error messages from intentional throws in tests.
    if (
      first.includes("PanelErrorBoundary caught error") ||
      first.includes("test error") ||
      first.includes("toggled error") ||
      first.includes("The above error occurred in the") ||
      first.includes("Error: test error") ||
      first.includes("Error: toggled error") ||
      // React 18 re-logs uncaught errors in test environment
      first.includes("react-dom") ||
      first.includes("ReactDOM") ||
      first.includes("AlwaysThrows") ||
      first.includes("TogglablePanel") ||
      first.includes("Consider adding an error boundary")
    ) {
      return;
    }
    originalError(...args);
  };
});

afterAll(() => {
  console.error = originalError;
});

// ---------------------------------------------------------------------------
// (a) + (b) -- child that throws shows honest fallback, boundary does not rethrow
// ---------------------------------------------------------------------------

describe("PanelErrorBoundary (a+b) -- error fallback is shown and does not rethrow", () => {
  it("renders the honest fallback when a child throws during render", () => {
    render(
      <PanelErrorBoundary label="Test Panel">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    // Fallback text must be visible
    expect(
      screen.getByText(/this panel hit an error/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/the rest of the page is unaffected/i),
    ).toBeInTheDocument();
  });

  it("carries data-honest-state=panel-error on the fallback wrapper", () => {
    const { container } = render(
      <PanelErrorBoundary label="Test Panel">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    expect(
      container.querySelector('[data-honest-state="panel-error"]'),
    ).not.toBeNull();
  });

  it("does NOT rethrow (the render completes without propagating the error)", () => {
    expect(() =>
      render(
        <PanelErrorBoundary label="Test Panel">
          <AlwaysThrows />
        </PanelErrorBoundary>,
      ),
    ).not.toThrow();
  });

  it("does NOT render children when they threw (no partial child output)", () => {
    const { container } = render(
      <PanelErrorBoundary label="Test Panel">
        <AlwaysThrows />
        <div data-testid="sibling">sibling</div>
      </PanelErrorBoundary>,
    );
    // Neither the throwing child nor its sibling should appear
    expect(screen.queryByTestId("sibling")).toBeNull();
    // The fallback is shown instead
    expect(container.querySelector('[data-honest-state="panel-error"]')).not.toBeNull();
  });

  it("uses role=status on the fallback (informational, not an assertive alert)", () => {
    const { container } = render(
      <PanelErrorBoundary label="Bets Panel">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    const fallback = container.querySelector('[data-honest-state="panel-error"]');
    expect(fallback?.getAttribute("role")).toBe("status");
  });

  it("carries the panel label in aria-label on the fallback wrapper", () => {
    render(
      <PanelErrorBoundary label="Live Scores">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    expect(
      screen.getByRole("status", { name: /live scores panel error/i }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// (c) -- healthy child renders unchanged (boundary is transparent)
// ---------------------------------------------------------------------------

describe("PanelErrorBoundary (c) -- healthy child renders unchanged", () => {
  it("passes through healthy children without wrapping visible DOM", () => {
    render(
      <PanelErrorBoundary label="Healthy Panel">
        <HealthyPanel text="all good" />
      </PanelErrorBoundary>,
    );
    expect(screen.getByTestId("healthy-panel")).toBeInTheDocument();
    expect(screen.getByText("all good")).toBeInTheDocument();
  });

  it("does NOT render the error fallback for a healthy child", () => {
    const { container } = render(
      <PanelErrorBoundary label="Healthy Panel">
        <HealthyPanel />
      </PanelErrorBoundary>,
    );
    expect(
      container.querySelector('[data-honest-state="panel-error"]'),
    ).toBeNull();
  });

  it("does NOT show the retry button when healthy", () => {
    render(
      <PanelErrorBoundary label="Healthy Panel">
        <HealthyPanel />
      </PanelErrorBoundary>,
    );
    expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
  });

  it("renders multiple healthy children without modification", () => {
    render(
      <PanelErrorBoundary label="Multi Child">
        <HealthyPanel text="child one" />
        <HealthyPanel text="child two" />
      </PanelErrorBoundary>,
    );
    expect(screen.getByText("child one")).toBeInTheDocument();
    expect(screen.getByText("child two")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// (d) -- retry/reset re-attempts to render children
// ---------------------------------------------------------------------------

describe("PanelErrorBoundary (d) -- retry/reset control re-attempts children", () => {
  it("shows a retry button after catching a render error", () => {
    render(
      <PanelErrorBoundary label="Retry Test">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    const retryBtn = screen.getByRole("button", { name: /retry retry test panel/i });
    expect(retryBtn).toBeInTheDocument();
  });

  it("clicking retry clears the error state (generation increments, children re-render)", () => {
    // Approach: use a parent wrapper component that owns a `shouldThrow` flag.
    // The boundary's children are controlled by the wrapper. After the initial
    // error we change the flag via wrapper's rerender so children stop throwing,
    // then click retry. This proves the reset + recovery path end-to-end.
    //
    // We use `rerender` from RTL to swap the outer wrapper's shouldThrow prop.
    function Wrapper({ shouldThrow }: { shouldThrow: boolean }): ReactNode {
      return (
        <PanelErrorBoundary label="Recovery Test">
          {shouldThrow ? (
            <AlwaysThrows message="toggled" />
          ) : (
            <HealthyPanel text="recovered successfully" />
          )}
        </PanelErrorBoundary>
      );
    }

    const { rerender } = render(<Wrapper shouldThrow={true} />);

    // Initial error -> fallback shown
    expect(screen.getByText(/this panel hit an error/i)).toBeInTheDocument();

    // Stop throwing (update the wrapper so children will be healthy on next render)
    rerender(<Wrapper shouldThrow={false} />);

    // Now click retry: the boundary resets (hasError=false, generation++) and
    // re-renders children; since shouldThrow is now false, they render healthy.
    const retryBtn = screen.getByRole("button", { name: /retry recovery test panel/i });
    act(() => {
      fireEvent.click(retryBtn);
    });

    // Healthy child should now be visible
    expect(screen.getByText("recovered successfully")).toBeInTheDocument();
    expect(screen.queryByText(/this panel hit an error/i)).toBeNull();
  });

  it("if child still throws after retry, the fallback is shown again", () => {
    render(
      <PanelErrorBoundary label="Persistent Error">
        <AlwaysThrows message="persistent" />
      </PanelErrorBoundary>,
    );

    // First error
    expect(screen.getByText(/this panel hit an error/i)).toBeInTheDocument();

    // Retry
    const retryBtn = screen.getByRole("button", { name: /retry persistent error panel/i });
    fireEvent.click(retryBtn);

    // Still erroring -> fallback shown again
    expect(screen.getByText(/this panel hit an error/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// (e) -- noRetry prop suppresses the retry button
// ---------------------------------------------------------------------------

describe("PanelErrorBoundary (e) -- noRetry prop suppresses the retry button", () => {
  it("does NOT render a retry button when noRetry=true", () => {
    render(
      <PanelErrorBoundary label="No Retry Panel" noRetry>
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    // Fallback is still shown
    expect(screen.getByText(/this panel hit an error/i)).toBeInTheDocument();
    // But no retry button
    expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
  });

  it("retry button IS shown by default (noRetry defaults to false)", () => {
    render(
      <PanelErrorBoundary label="Default Retry">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    expect(screen.getByRole("button", { name: /retry default retry panel/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// (f) -- tone invariants: no red or green classes in the error fallback
// ---------------------------------------------------------------------------

describe("PanelErrorBoundary (f) -- tone invariants: no red, no green on error fallback", () => {
  it("error fallback contains no red tone classes", () => {
    const { container } = render(
      <PanelErrorBoundary label="Tone Test">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    const html = container.innerHTML;
    expect(html).not.toContain("bg-red");
    expect(html).not.toContain("text-red-");
    expect(html).not.toContain("border-red-");
  });

  it("error fallback contains no green tone classes (never goes green)", () => {
    const { container } = render(
      <PanelErrorBoundary label="Tone Test">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    const html = container.innerHTML;
    expect(html).not.toContain("bg-green");
    expect(html).not.toContain("text-green-");
    expect(html).not.toContain("tier-a");
    expect(html).not.toContain("bg-success");
  });

  it("error fallback is neutral amber (the expected tone)", () => {
    const { container } = render(
      <PanelErrorBoundary label="Amber Test">
        <AlwaysThrows />
      </PanelErrorBoundary>,
    );
    const fallback = container.querySelector('[data-honest-state="panel-error"]');
    expect(fallback?.className).toContain("amber");
  });

  it("healthy state output contains no error fallback classes", () => {
    const { container } = render(
      <PanelErrorBoundary label="Healthy Tone">
        <HealthyPanel />
      </PanelErrorBoundary>,
    );
    expect(
      container.querySelector('[data-honest-state="panel-error"]'),
    ).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// (g) -- withPanelErrorBoundary convenience wrapper
// ---------------------------------------------------------------------------

describe("PanelErrorBoundary (g) -- withPanelErrorBoundary convenience wrapper", () => {
  it("wraps a throwing node and shows the honest fallback", () => {
    render(
      <>{withPanelErrorBoundary("Convenience Panel", <AlwaysThrows />)}</>,
    );
    expect(screen.getByText(/this panel hit an error/i)).toBeInTheDocument();
  });

  it("wraps a healthy node and passes it through transparently", () => {
    render(
      <>{withPanelErrorBoundary("Healthy Wrapper", <HealthyPanel text="via wrapper" />)}</>,
    );
    expect(screen.getByText("via wrapper")).toBeInTheDocument();
  });

  it("respects noRetry option passed via opts", () => {
    render(
      <>
        {withPanelErrorBoundary("No Retry", <AlwaysThrows />, { noRetry: true })}
      </>,
    );
    expect(screen.getByText(/this panel hit an error/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Boundary isolation: one boundary catching does not affect siblings
// ---------------------------------------------------------------------------

describe("PanelErrorBoundary isolation -- one caught boundary does not affect siblings", () => {
  it("a sibling PanelErrorBoundary that is healthy renders correctly alongside a caught one", () => {
    render(
      <div>
        <PanelErrorBoundary label="Broken Panel">
          <AlwaysThrows />
        </PanelErrorBoundary>
        <PanelErrorBoundary label="Healthy Sibling">
          <HealthyPanel text="I am fine" />
        </PanelErrorBoundary>
      </div>,
    );
    // Broken panel shows fallback
    expect(screen.getByText(/this panel hit an error/i)).toBeInTheDocument();
    // Healthy sibling renders normally
    expect(screen.getByText("I am fine")).toBeInTheDocument();
  });

  it("two broken panels each show their own independent fallback", () => {
    const { container } = render(
      <div>
        <PanelErrorBoundary label="Panel A">
          <AlwaysThrows message="error A" />
        </PanelErrorBoundary>
        <PanelErrorBoundary label="Panel B">
          <AlwaysThrows message="error B" />
        </PanelErrorBoundary>
      </div>,
    );
    const fallbacks = container.querySelectorAll('[data-honest-state="panel-error"]');
    expect(fallbacks.length).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// Never-crash invariant: does not throw under all edge inputs
// ---------------------------------------------------------------------------

describe("PanelErrorBoundary never-crash invariant -- renders safely under all inputs", () => {
  it("renders without throwing when child is a simple string", () => {
    expect(() =>
      render(
        <PanelErrorBoundary label="String Child">
          just a string
        </PanelErrorBoundary>,
      ),
    ).not.toThrow();
  });

  it("renders without throwing when child is null", () => {
    expect(() =>
      render(
        <PanelErrorBoundary label="Null Child">
          {null}
        </PanelErrorBoundary>,
      ),
    ).not.toThrow();
  });

  it("renders without throwing when there are no children", () => {
    // TypeScript would normally flag this, but we test runtime resilience.
    expect(() =>
      render(
        <PanelErrorBoundary label="Empty">
          {/* intentionally empty */}
          {null}
        </PanelErrorBoundary>,
      ),
    ).not.toThrow();
  });

  it("handles nested PanelErrorBoundary (composable -- each catches its own subtree)", () => {
    expect(() =>
      render(
        <PanelErrorBoundary label="Outer">
          <PanelErrorBoundary label="Inner">
            <AlwaysThrows />
          </PanelErrorBoundary>
          <HealthyPanel text="outer healthy child" />
        </PanelErrorBoundary>,
      ),
    ).not.toThrow();
    // Inner caught the error; outer + outer's other child remain healthy
    expect(screen.getByText("outer healthy child")).toBeInTheDocument();
  });
});
