// PanelErrorBoundary.tsx -- WS2 primitive: class-based React error boundary.
// Catches render errors in a panel subtree and degrades to an honest fallback
// instead of propagating to a white route. Never shows red/failed; neutral amber
// "unavailable" tone consistent with the stale-never-green and UNITS-only rails.
//
// Usage:
//   <PanelErrorBoundary label="best bets board">
//     <BestBetsBoard />
//   </PanelErrorBoundary>
//
// LOC <= 80 (target); class component required by React error boundary API.

import { Component } from "react";
import type { ReactNode, ErrorInfo } from "react";

// FallbackPanel -- honest degraded state rendered when a child subtree throws.
// Matches the Unavailable tone from Primitives without importing to avoid cycles.
function FallbackPanel({ label, detail }: { label: string; detail?: string }) {
  return (
    <div
      role="status"
      aria-label={`${label} unavailable`}
      data-testid="panel-error-fallback"
      className="flex flex-col gap-1 rounded-lg border border-amber-900/40 bg-amber-950/20 px-4 py-4 text-sm"
    >
      <span className="font-mono text-amber-400">unavailable</span>
      <span className="text-[11px] text-muted-foreground">
        {label} could not be displayed. Reload the page to retry.
      </span>
      {detail ? (
        <span className="font-mono text-[10px] text-faint">{detail}</span>
      ) : null}
    </div>
  );
}

interface Props {
  children: ReactNode;
  /** Human-readable label for the fallback message (e.g. "best bets board"). */
  label: string;
}

interface State {
  hasError: boolean;
  detail: string | undefined;
}

export class PanelErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, detail: undefined };
  }

  static getDerivedStateFromError(error: unknown): State {
    const detail =
      error instanceof Error ? error.message : String(error);
    return { hasError: true, detail };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    // Surface to console for debugging; never throw or re-render.
    // Keep this a no-op for production beyond logging.
    if (process.env.NODE_ENV !== "production") {
      console.error("[PanelErrorBoundary]", this.props.label, error, info);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <FallbackPanel
          label={this.props.label}
          detail={
            process.env.NODE_ENV !== "production"
              ? this.state.detail
              : undefined
          }
        />
      );
    }
    return this.props.children;
  }
}
