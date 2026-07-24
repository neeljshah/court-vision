// app/loading.tsx -- global route-level loading state (Next.js Suspense boundary).
// Shows a skeleton placeholder while the route is loading.

export default function GlobalLoading() {
  return (
    <div
      role="status"
      aria-label="Loading"
      className="mx-auto flex max-w-7xl flex-col gap-4 p-6"
    >
      {/* Skeleton rows that match the rough shape of the dashboard */}
      <div className="skeleton-shimmer h-6 w-48 rounded" />
      <div className="grid grid-cols-12 gap-4">
        <div className="skeleton-shimmer col-span-12 h-48 rounded-xl lg:col-span-7" />
        <div className="col-span-12 flex flex-col gap-4 lg:col-span-5">
          <div className="skeleton-shimmer h-24 rounded-xl" />
          <div className="skeleton-shimmer h-20 rounded-xl" />
        </div>
      </div>
      <div className="skeleton-shimmer h-32 rounded-xl" />
      <div className="grid grid-cols-12 gap-4">
        <div className="skeleton-shimmer col-span-12 h-40 rounded-xl lg:col-span-7" />
        <div className="skeleton-shimmer col-span-12 h-40 rounded-xl lg:col-span-5" />
      </div>
      <span className="sr-only">Loading dashboard...</span>
    </div>
  );
}
