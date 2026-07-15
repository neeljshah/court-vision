"use client";

// PanelErrorBoundary -- reusable React class-based ErrorBoundary for in-panel
// render/runtime crashes.
//
// HONESTY RAILS (mirrors RAILS in workstream spec):
//   - Catches child render errors via getDerivedStateFromError + componentDidCatch.
//   - Renders an honest neutral amber fallback: "this panel hit an error -- the
//     rest of the page is unaffected". NEVER blank, NEVER green, NEVER red.
//   - Optional retry/reset button clears error state and re-attempts children.
//   - Never shows raw error strings or fabricated data to the user.
//   - Error is logged to console only (not surfaced as user-visible text).
//   - ASCII only. <=300 LOC.
//
// Usage:
//   import { PanelErrorBoundary } from "@/components/honest/PanelErrorBoundary";
//
//   <PanelErrorBoundary label="Top Bets">
//     <TopBetsPanel />
//   </PanelErrorBoundary>
//
// The label prop names the panel for console logs and the aria-label on the
// fallback wrapper. It does NOT appear in the visible user-facing text (panel
// names are internal). The only user-visible copy is the honest fallback.

import { Component, type ReactNode, type ErrorInfo } from "react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PanelErrorBoundaryProps {
  /**
   * Human-readable panel name used in console logs and the aria-label on the
   * fallback region. NOT shown to the user in visible text.
   */
  label: string;
  /** Child tree to render while healthy. */
  children: ReactNode;
  /**
   * Optional: additional CSS class forwarded to the fallback wrapper div.
   * The healthy-state wrapper does NOT receive this class (pass-through only).
   */
  className?: string;
  /**
   * Optional: when true, hides the retry button even when an error is caught.
   * Default false (retry shown). Useful for panels where re-mounting is
   * unlikely to help (e.g. a panel that depends on missing required context).
   */
  noRetry?: boolean;
}

interface State {
  /** Whether a render error has been caught. */
  hasError: boolean;
  /**
   * Opaque generation counter: incrementing it forces React to remount
   * children after reset, re-running their constructors + effects.
   */
  generation: number;
}

// ---------------------------------------------------------------------------
// PanelErrorBoundary
// ---------------------------------------------------------------------------

/**
 * PanelErrorBoundary -- React class-based ErrorBoundary.
 *
 * Wraps any panel surface. When the child tree throws during render or a
 * lifecycle, the boundary catches and shows the honest neutral fallback
 * instead of crashing the entire route or page. The rest of the UI is
 * unaffected.
 *
 * Must be a class component: React ErrorBoundary APIs (getDerivedStateFromError,
 * componentDidCatch) are only available on class components. The "use client"
 * directive at the top of the file satisfies Next.js's requirement that
 * boundaries live in client components.
 */
export class PanelErrorBoundary extends Component<
  PanelErrorBoundaryProps,
  State
> {
  constructor(props: PanelErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, generation: 0 };
    this.handleReset = this.handleReset.bind(this);
  }

  // Called synchronously during the render phase when a descendant throws.
  // Returns the state delta; does NOT perform side-effects.
  static getDerivedStateFromError(_error: unknown): Partial<State> {
    return { hasError: true };
  }

  // Called after the boundary has rendered the fallback, in the commit phase.
  // Safe to perform side-effects here (logging).
  componentDidCatch(error: unknown, info: ErrorInfo): void {
    // Console only -- raw error strings are NEVER surfaced to the user.
    console.error(
      `[CourtVision] PanelErrorBoundary caught error in panel "${this.props.label}":`,
      error,
      info.componentStack ?? "",
    );
  }

  // Reset: increment the generation key so React unmounts+remounts the child
  // tree from scratch, giving it a clean slate. This is more reliable than
  // merely clearing hasError when the error is in component initialisation.
  handleReset(): void {
    this.setState((prev) => ({
      hasError: false,
      generation: prev.generation + 1,
    }));
  }

  render(): ReactNode {
    const { hasError, generation } = this.state;
    const { children, label, className, noRetry = false } = this.props;

    if (hasError) {
      return (
        <div
          role="status"
          aria-label={`${label} panel error -- isolated`}
          data-honest-state="panel-error"
          data-panel-label={label}
          className={cn(
            "flex flex-col gap-2 rounded-lg border border-amber-900/40",
            "bg-amber-950/20 px-3 py-3 text-sm",
            className,
          )}
        >
          {/* State label -- matches HonestState tone palette; amber, never green */}
          <span className="font-mono text-xs uppercase tracking-wide text-amber-400">
            panel error
          </span>

          {/* Honest, user-facing explanation -- no fabricated data, no raw errors */}
          <p className="text-xs leading-relaxed text-muted-foreground">
            This panel hit an error -- the rest of the page is unaffected.
          </p>

          {/* Retry / reset control -- optional, default shown */}
          {!noRetry && (
            <button
              type="button"
              onClick={this.handleReset}
              aria-label={`Retry ${label} panel`}
              className={cn(
                "mt-1 self-start rounded border border-amber-800/50 bg-amber-950/30",
                "px-2 py-0.5 font-mono text-xs text-amber-400",
                "hover:bg-amber-900/30 transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-600",
              )}
            >
              retry
            </button>
          )}
        </div>
      );
    }

    // Healthy path: render children keyed by generation so that a reset
    // forces a full remount of the child tree.
    return (
      // Key-wrapped fragment: React needs a DOM element or fragment with the
      // key to trigger remount on generation change. A keyed span wrapper
      // with display:contents avoids injecting a layout-affecting element.
      <span
        key={generation}
        data-panel-generation={generation}
        style={{ display: "contents" }}
      >
        {children}
      </span>
    );
  }
}

// ---------------------------------------------------------------------------
// Convenience functional wrapper (tree-shakeable; re-exports the class above)
// ---------------------------------------------------------------------------

/**
 * withPanelErrorBoundary -- wraps a ReactNode in a PanelErrorBoundary.
 * Useful for one-liners where JSX wrapping feels verbose.
 *
 *   {withPanelErrorBoundary("Bets", <TopBetsPanel />)}
 */
export function withPanelErrorBoundary(
  label: string,
  node: ReactNode,
  opts?: { noRetry?: boolean; className?: string },
): ReactNode {
  return (
    <PanelErrorBoundary label={label} {...opts}>
      {node}
    </PanelErrorBoundary>
  );
}
