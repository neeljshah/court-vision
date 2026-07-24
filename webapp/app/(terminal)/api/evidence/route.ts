// GET /api/evidence -- same-origin, file-backed reader for the m44 append-only
// evidence series. Mirrors the bestbets disk-route pattern: force-static/503
// stub for the snapshot export build, no dynamic segments so no
// generateStaticParams needed. Reducer + types live in ./_lib (Next route
// modules may only export handlers/config).

import { promises as fs } from "node:fs";
import { NextResponse } from "next/server";
import { EVIDENCE_SERIES_PATH, reduceSeries, type EvidenceResponse } from "./_lib";

// Snapshot demo build (output:'export') can't ship a force-dynamic route.
export const dynamic =
  process.env.NEXT_PUBLIC_DATA_MODE === "snapshot" ? "force-static" : "force-dynamic";
export const runtime = "nodejs";

function unavailable(reason: string) {
  return NextResponse.json(
    {
      status: "unavailable",
      series_by_market: {},
      latest: {},
      n_vintages: 0,
      as_of: null,
      reason,
    } satisfies EvidenceResponse,
    { status: 503 },
  );
}

export async function GET() {
  if (process.env.NEXT_PUBLIC_DATA_MODE === "snapshot") {
    return unavailable("static demo build -- no evidence series file");
  }
  let stat;
  try {
    stat = await fs.stat(EVIDENCE_SERIES_PATH);
  } catch {
    return unavailable(
      "exec_evidence_series.jsonl missing -- the m44 daemon has not written a vintage yet",
    );
  }
  let raw: string;
  try {
    raw = await fs.readFile(EVIDENCE_SERIES_PATH, "utf-8");
  } catch {
    return unavailable("exec_evidence_series.jsonl unreadable");
  }
  const reduced = reduceSeries(raw.split("\n"));
  return NextResponse.json({
    status: "ok",
    as_of: stat.mtime.toISOString(),
    ...reduced,
  } satisfies EvidenceResponse);
}
