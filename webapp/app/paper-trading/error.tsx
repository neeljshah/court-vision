"use client";

// app/paper-trading/error.tsx -- route-level error boundary.
// Shows a clean recovery UI if the page throws an unhandled error.
// NEVER displays raw error strings to the user.
// Matches the global error.tsx pattern.

import { useEffect } from "react";

export default function PaperTradingError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log only -- never surface raw error strings in the UI.
    console.error("[PaperTrading] unhandled error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 p-8 text-center">
      <span className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
        paper trading system unavailable
      </span>
      <p className="max-w-sm text-sm text-muted-foreground">
        The paper-trading data feed could not be loaded. The backend may be
        starting up or temporarily unavailable. No action is needed -- this
        view never fabricates results.
      </p>
      <div
        role="alert"
        aria-label="Real money is DENIED -- paper mode only"
        className="rounded-lg border border-amber-900/50 bg-amber-950/20 px-4 py-2 text-[11px] text-amber-400"
      >
        Real-money: DENY. Paper mode only.
      </div>
      <button
        onClick={reset}
        className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Try again
      </button>
    </div>
  );
}
