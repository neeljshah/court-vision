// app/not-found.tsx -- custom 404 page.
import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 p-8 text-center">
      <span className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
        404 -- not found
      </span>
      <p className="max-w-sm text-sm text-muted-foreground">
        This page or game does not exist. The slate may have changed or the link
        is outdated.
      </p>
      <Link
        href="/p6"
        className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Back to dashboard
      </Link>
    </div>
  );
}
