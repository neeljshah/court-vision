"use client";

// /paper route error boundary.
//
// Next.js renders this component when the /paper segment throws an unhandled
// error during render or data fetching. It provides an honest, recoverable
// degraded state instead of a blank white screen.
//
// Contract:
//   - Never shows a blank page.
//   - Never shows a red "failed" terminal state -- always offers a retry.
//   - No dollar or edge-claim text.
//   - The `reset` callback re-renders the segment from scratch (Next.js 13+).

import { useEffect } from "react";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function PaperError({ error, reset }: ErrorProps) {
  // Log to console so devtools surface the root cause without exposing it in
  // the UI (which could leak internal detail to end users).
  useEffect(() => {
    console.error("[paper] unhandled segment error:", error);
  }, [error]);

  return (
    <div
      role="alert"
      data-testid="paper-error-boundary"
      className="mx-auto max-w-xl px-4 py-16 text-center"
    >
      <p className="text-sm font-semibold text-amber-400">
        Paper trail temporarily unavailable
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        The page encountered an unexpected error. No data has been lost -- paper
        trades are stored server-side. Retry to reload the latest snapshot.
      </p>
      <p className="mt-1 text-[11px] text-faint">
        All values are UNITS, never dollars. No edge is claimed.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 rounded-full border border-slate-700 px-5 py-1.5 text-xs text-foreground hover:border-slate-500 hover:text-foreground transition-colors"
      >
        Retry
      </button>
    </div>
  );
}
