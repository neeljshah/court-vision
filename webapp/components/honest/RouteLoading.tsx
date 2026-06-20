// RouteLoading -- the shared body for every per-route loading.tsx boundary.
//
// Next.js renders a segment's loading.tsx during its Suspense boundary so a
// navigating user sees a calm skeleton instead of a blank frame or a spinner
// that can hang forever. This is bounded chrome only -- it never implies data
// exists; the real panels resolve to live data OR to an honest HonestState.

export function RouteLoading({ label = "Loading" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-label={label}
      className="mx-auto flex max-w-7xl flex-col gap-4 p-6"
    >
      <div className="skeleton-shimmer h-6 w-48 rounded" />
      <div className="grid grid-cols-12 gap-4">
        <div className="skeleton-shimmer col-span-12 h-40 rounded-xl lg:col-span-7" />
        <div className="col-span-12 flex flex-col gap-4 lg:col-span-5">
          <div className="skeleton-shimmer h-24 rounded-xl" />
          <div className="skeleton-shimmer h-20 rounded-xl" />
        </div>
      </div>
      <div className="skeleton-shimmer h-32 rounded-xl" />
      <span className="sr-only">{label}...</span>
    </div>
  );
}
