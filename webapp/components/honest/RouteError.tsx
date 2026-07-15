"use client";

// RouteError -- the shared body for every per-route error.tsx boundary.
//
// When a route segment's render throws (a bad payload shape, an unexpected
// runtime error), Next.js renders the segment's error.tsx instead of a white
// screen. This component is the ONE honest recovery UI: it names the section,
// never prints the raw error string to the user, and offers a retry. It mirrors
// the global app/error.tsx but is scoped so one broken page never blanks the
// whole shell. NO fabricated data is ever shown -- a failed view degrades to this.

import { useEffect } from "react";

export function RouteError({
  section,
  error,
  reset,
}: {
  section: string;
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Console only -- raw error strings are never shown to the user.
    console.error(`[CourtVision] ${section} route error:`, error);
  }, [section, error]);

  return (
    <div className="mx-auto flex min-h-[40vh] max-w-2xl flex-col items-center justify-center gap-4 p-8 text-center">
      <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-amber-400">
        {section} unavailable
      </span>
      <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">
        This view failed to load. The data feed may be unavailable or still
        starting up. Nothing here is fabricated -- when data is missing the page
        says so rather than guessing a number.
      </p>
      <button
        onClick={reset}
        className="rounded-md border border-slate-700 px-4 py-2 text-sm font-medium text-slate-200 transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-500"
      >
        Try again
      </button>
    </div>
  );
}
