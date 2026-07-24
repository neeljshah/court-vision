// app/bets/loading.tsx -- skeleton loading state for the Bets page.
//
// Next.js Suspense boundary renders this while the route hydrates.
// Uses skeleton-shimmer to show the approximate card-grid layout.
// No data is implied -- just chrome shape.

import { RouteLoading } from "@/components/honest/RouteLoading";

export default function BetsLoading() {
  return <RouteLoading label="Loading best bets board" />;
}
