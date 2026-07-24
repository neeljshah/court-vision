"use client";

// app/error.tsx -- global error boundary for unhandled client errors.
// Shows a clean recovery UI instead of a white screen.

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to console only -- never display raw error strings to users.
    console.error("[CourtVision] unhandled error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 p-8 text-center">
      <span className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
        something went wrong
      </span>
      <p className="max-w-sm text-sm text-muted-foreground">
        A component failed to load. The data feed may be unavailable or still
        starting up. No action is needed -- this view never fabricates results.
      </p>
      <button
        onClick={reset}
        className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Try again
      </button>
    </div>
  );
}
