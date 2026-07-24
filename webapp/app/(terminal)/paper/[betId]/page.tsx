// Server wrapper -- exists only to carry generateStaticParams (a "use client"
// file can't export it). All rendering lives in BetDetailPageClient, which
// reads the betId param itself via useParams().
import { readManifest } from "@/lib/manifest.server";
import BetDetailPageClient from "./BetDetailPageClient";

// Static export (output:'export') requires every path to be pre-rendered --
// no server exists to handle an unlisted param. Live/dev builds keep true so
// any sport/gameId still renders on demand.
export const dynamicParams = process.env.NEXT_PUBLIC_DATA_MODE !== "snapshot";

export async function generateStaticParams() {
  const m = await readManifest();
  const ids = m?.bet_ids ?? [];
  // output:'export' errors if a dynamic route resolves to 0 static paths --
  // fall back to a placeholder id (renders the existing honest "not found").
  return (ids.length ? ids : ["none"]).map((betId) => ({ betId }));
}

export default function BetDetailPage() {
  return <BetDetailPageClient />;
}
