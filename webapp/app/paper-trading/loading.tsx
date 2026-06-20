// app/paper-trading/loading.tsx -- route-level Suspense loading skeleton.
// Matches the rough shape of the paper-trading page: tally strip + table area.
// Never red, never "failed" -- absence of data is not an error.

export default function PaperTradingLoading() {
  return (
    <div
      role="status"
      aria-label="Loading paper trading system"
      className="mx-auto max-w-6xl px-4 py-8"
    >
      {/* Page header skeleton */}
      <div className="mb-6">
        <div className="skeleton-shimmer h-6 w-56 rounded" />
        <div className="skeleton-shimmer mt-2 h-4 w-80 rounded" />
      </div>

      {/* DENY banner skeleton */}
      <div className="skeleton-shimmer mb-5 h-10 w-full rounded-lg" />

      {/* Tally strip skeleton: 7 tiles */}
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        {Array.from({ length: 7 }).map((_, i) => (
          <div
            key={i}
            className="rounded-lg border border-slate-800 bg-bg-subtle px-3 py-3"
          >
            <div className="skeleton-shimmer h-3 w-12 rounded" />
            <div className="skeleton-shimmer mt-2 h-7 w-10 rounded" />
          </div>
        ))}
      </div>

      {/* Venue summary placeholder skeleton */}
      <div className="skeleton-shimmer mb-5 h-12 w-full rounded-lg" />

      {/* Trade trail panel skeleton */}
      <div className="rounded-xl border border-slate-800 bg-bg-panel">
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2.5">
          <div className="skeleton-shimmer h-3 w-24 rounded" />
          <div className="skeleton-shimmer h-6 w-32 rounded-full" />
        </div>
        <div className="space-y-2 p-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="skeleton-shimmer h-9 w-full rounded" />
          ))}
        </div>
      </div>

      <span className="sr-only">Loading paper trading system...</span>
    </div>
  );
}
