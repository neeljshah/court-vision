// loading.tsx -- Next.js loading UI for /live (shown while the page shell
// hydrates before LiveGamesView's first client-side poll completes).
// Matches the dark panel skeleton pattern used across the app.

export default function LiveLoading() {
  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="skeleton-shimmer h-8 w-48" />
        <div className="skeleton-shimmer h-6 w-32" />
      </div>
      <div className="flex flex-col gap-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="skeleton-shimmer h-16" />
        ))}
      </div>
    </main>
  );
}
