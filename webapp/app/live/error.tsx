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
      <div className="flex flex-col items-center gap-4 rounded-xl border border-amber-900/40 bg-amber-950/20 px-8 py-10 text-center">
        <span className="font-mono text-sm font-semibold uppercase tracking-wide text-amber-400">
          live page unavailable
        </span>
        <p className="text-[12px] text-slate-400">
          The live games surface could not load. The predict service may be
          offline or starting up. Auto-refresh will resume when it recovers.
        </p>
        <button
          type="button"
          onClick={reset}
          className="mt-2 rounded border border-slate-700 bg-slate-900 px-4 py-1.5 font-mono text-xs text-slate-300 transition-colors hover:border-slate-500 hover:text-slate-100"
        >
          try again
        </button>
      </div>
    </main>
  );
}
