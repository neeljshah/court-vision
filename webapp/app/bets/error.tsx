"use client";

// app/bets/error.tsx -- error boundary for the Bets route.
//
// When the Bets board segment throws (bad payload, network error, etc.),
// Next.js renders this instead of a white screen. Never prints raw error
// strings. Offers a retry. The model never fabricates a result when data
// is missing -- this view makes that explicit.

import { RouteError } from "@/components/honest/RouteError";

export default function BetsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError section="Best Bets" error={error} reset={reset} />;
}
