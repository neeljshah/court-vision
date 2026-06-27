// GET /api/paper/today -- READ-ONLY "today" digest for the webapp.
//
// Reads data/frontend/paper_today.json (written by the daily paper cycle) straight
// off disk, server-side, and serves it to the Home TODAY digest + the /today view.
// This route ONLY reads -- it never writes data/, never creates a sentinel, never
// flips a flag, never starts a process.
//
// Shape served (passed through verbatim when present):
//   { date, placed:[...], pending:[...], settled_today:[...],
//     day_units, cumulative_units, bankroll, start_units }
//
// HONESTY RAILS:
//   - UNITS only -- NO $ field is ever emitted or fabricated.
//   - edge_claimed is always false.
//   - If the file is missing / torn the route degrades to an explicit
//     status="unavailable" 503 (NEVER a fabricated digest). The client then
//     falls back to the live endpoints and degrades honestly from there.
//   - stale-never-green: when the file carries a `date` we surface it verbatim so
//     the UI can flag an out-of-date digest; we never claim freshness we lack.

import { NextResponse } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic"; // never cache a daily-cycle read
export const runtime = "nodejs";

// Repo root is the webapp's parent dir. The daily cycle writes the canonical doc
// to data/frontend/paper_today.json relative to the repo root.
const TODAY_PATH = path.join(
  process.cwd(),
  process.cwd().endsWith("webapp") ? ".." : ".",
  "data",
  "frontend",
  "paper_today.json",
);

function unavailable(reason: string) {
  // Honest degrade: never a fabricated digest, never a $ field.
  return NextResponse.json(
    {
      status: "unavailable",
      reason,
      edge_claimed: false,
    },
    { status: 503 },
  );
}

export async function GET() {
  let raw: string;
  try {
    raw = await fs.readFile(TODAY_PATH, "utf-8");
  } catch {
    return unavailable("paper_today.json missing or unreadable");
  }

  let doc: Record<string, unknown>;
  try {
    doc = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return unavailable("paper_today.json torn / not JSON");
  }

  // Pass the document through verbatim; force the honesty rails on the envelope so
  // the client can rely on them regardless of what the writer emitted.
  return NextResponse.json({
    status: typeof doc.status === "string" ? doc.status : "ok",
    ...doc,
    edge_claimed: false,
  });
}
