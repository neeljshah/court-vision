// app/records/loading.tsx -- W1-records-surface: skeleton shown by Next.js
// Suspense streaming while the page shell is SSR-ing. ASCII only.

export default function RecordsLoading() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 space-y-4" aria-busy="true" aria-label="loading records">
      {/* Header skeleton */}
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-1.5">
          <div className="h-4 w-52 animate-pulse bg-surface-2" />
          <div className="h-3 w-80 animate-pulse bg-surface-2" />
        </div>
        <div className="h-6 w-28 animate-pulse bg-surface-2" />
      </div>

      {/* Filter bar skeleton */}
      <div className="flex gap-3">
        {["w-20", "w-20", "w-16"].map((wCls, i) => (
          <div key={i} className={`h-7 ${wCls} animate-pulse bg-surface-2`} />
        ))}
      </div>

      {/* Summary strip skeleton */}
      <div className="flex gap-6 border border-border bg-card px-4 py-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-8 w-14 animate-pulse bg-surface-2" />
        ))}
      </div>

      {/* Table skeleton */}
      <div className="space-y-2">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="h-7 w-full animate-pulse bg-surface-2" role="presentation" />
        ))}
      </div>
    </main>
  );
}
