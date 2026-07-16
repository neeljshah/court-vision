// Server wrapper -- exists only to carry generateStaticParams (a "use client"
// file can't export it). All rendering lives in SportBetsPageClient, which
// reads the sport param itself via useParams().
import { readManifest } from "@/lib/manifest.server";
import SportBetsPageClient from "./SportBetsPageClient";

// Static export (output:'export') requires every path to be pre-rendered --
// no server exists to handle an unlisted param. Live/dev builds keep true so
// any sport/gameId still renders on demand.
export const dynamicParams = process.env.NEXT_PUBLIC_DATA_MODE !== "snapshot";

export async function generateStaticParams() {
  const m = await readManifest();
  return (m?.sports ?? []).map((sport) => ({ sport }));
}

export default function SportBetsPage() {
  return <SportBetsPageClient />;
}
