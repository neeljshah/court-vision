import { NextRequest, NextResponse } from "next/server";

// Same-origin proxy to the :8098 boards API so the Bet Board works from any
// device that can reach the Next app (one origin, one tunnel, no CORS).
const UPSTREAM =
  process.env.BOARD_UPSTREAM || "http://127.0.0.1:8098";

// Snapshot demo build (output:'export') can't ship a dynamic route -- never
// called by the client there anyway (fetchHonest redirects to
// /demo-data/*.json first); stub it so the static export still builds.
export const dynamic =
  process.env.NEXT_PUBLIC_DATA_MODE === "snapshot" ? "force-static" : "force-dynamic";

export async function GET(req: NextRequest) {
  const sport = req.nextUrl.searchParams.get("sport") ?? "nba";
  if (process.env.NEXT_PUBLIC_DATA_MODE === "snapshot") {
    return NextResponse.json(
      { sport, status: "unavailable", games: [], note: "static demo build -- no boards service" },
      { status: 503 },
    );
  }
  try {
    const res = await fetch(
      `${UPSTREAM}/api/slate?sport=${encodeURIComponent(sport)}`,
      { cache: "no-store" },
    );
    // Short shared cache: bursty clients hit Next, not the boards service.
    return NextResponse.json(await res.json(), {
      status: res.status,
      headers: { "Cache-Control": "s-maxage=15, stale-while-revalidate=60" },
    });
  } catch {
    return NextResponse.json(
      { sport, status: "unavailable", games: [], note: "boards API unreachable" },
      { status: 503 },
    );
  }
}
