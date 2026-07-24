"use client";
// error.tsx -- Next.js error boundary for /live. Shows an honest "unavailable"
// state. The error boundary is a client component so it can catch client
// rendering errors. Does NOT expose internal error messages to the user.

import { useEffect } from "react";

export default function LiveError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to console in development; no external reporting.
    console.error("[/live error boundary]", error);
  }, [error]);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <div className="flex flex-col items-center gap-4 border border-warning/40 bg-card px-8 py-10 text-center">
        <span className="font-data text-sm font-semibold uppercase tracking-wide text-stale">
          live page unavailable
        </span>
        <p className="text-[12px] text-muted-foreground">
          The live games surface could not load. The predict service may be
          offline or starting up. Auto-refresh will resume when it recovers.
        </p>
        <button
          type="button"
          onClick={reset}
          className="mt-2 border border-border bg-surface-2 px-4 py-1.5 font-data text-xs text-muted-foreground transition-colors hover:border-primary/60 hover:text-foreground"
        >
          try again
        </button>
      </div>
    </main>
  );
}
