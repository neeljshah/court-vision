import { NextRequest, NextResponse } from "next/server";

// Same-origin proxy to the :8098 boards API so the Bet Board works from any
// device that can reach the Next app (one origin, one tunnel, no CORS).
const UPSTREAM =
  process.env.BOARD_UPSTREAM || "http://127.0.0.1:8098";

export async function GET(req: NextRequest) {
  const sport = req.nextUrl.searchParams.get("sport") ?? "nba";
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
