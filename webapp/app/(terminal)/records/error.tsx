"use client";

// app/records/error.tsx -- W1-records-surface: Next.js error boundary for /records.
// Shown on unhandled client or server errors. Degrades honestly, never crashes.
// ASCII only.

import { useEffect } from "react";

interface ErrorProps {
  error:  Error & { digest?: string };
  reset:  () => void;
}

export default function RecordsError({ error, reset }: ErrorProps) {
  useEffect(() => {
    // Log to console in development; production error reporters can pick this up.
    if (process.env.NODE_ENV !== "production") {
      console.error("[records/error]", error);
    }
  }, [error]);

  return (
    <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6 text-center">
      <p className="text-[13px] text-muted-foreground">
        Records temporarily unavailable.
      </p>
      <p className="mt-1 font-data text-[11px] text-faint">
        {error.message ?? "unknown error"}
      </p>
      <p className="mt-2 font-data text-[10px] text-faint">
        No edge is claimed. Units only. Try refreshing.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-4 border border-border bg-secondary px-3 py-1.5 font-data text-[11px] text-muted-foreground hover:border-ring hover:text-foreground transition-colors"
      >
        retry
      </button>
    </main>
  );
}
