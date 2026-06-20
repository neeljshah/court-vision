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
      <p className="text-[13px] text-slate-400">
        Records temporarily unavailable.
      </p>
      <p className="mt-1 font-mono text-[11px] text-slate-600">
        {error.message ?? "unknown error"}
      </p>
      <p className="mt-2 font-mono text-[10px] text-slate-700">
        No edge is claimed. Units only. Try refreshing.
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-4 rounded border border-slate-700 bg-slate-900 px-3 py-1.5 font-mono text-[11px] text-slate-300 hover:border-slate-500 transition-colors"
      >
        retry
      </button>
    </main>
  );
}
