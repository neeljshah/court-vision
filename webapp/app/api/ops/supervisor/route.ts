// GET /api/ops/supervisor -- READ-ONLY supervisor status for the webapp.
//
// Reads data/frontend/ops/supervisor_status.json (written by supervisor/status.py)
// straight off disk, server-side, and serves it to the LIVE indicator + the
// enriched System/Ops view. This route ONLY reads -- it never writes data/, never
// creates a sentinel, never flips a flag, never starts a process.
//
// HARD RAIL -- stale-never-green: the supervisor heartbeats `updated_at` every
// tick. If that timestamp is older than the SLA (or the file is missing / torn),
// we return live:false with an explicit reason and overall='down'/'degraded'.
// A green LIVE state is impossible unless the file is FRESH *and* all_ready is
// true *and* no proc is DEGRADED/DOWN. No $ field is ever emitted.

import { NextResponse } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";

// Snapshot demo build (output:'export') can't ship a force-dynamic route --
// this is never called by the client there anyway (fetchHonest redirects to
// /demo-data/*.json first); stub it so the static export still builds.
export const dynamic =
  process.env.NEXT_PUBLIC_DATA_MODE === "snapshot" ? "force-static" : "force-dynamic";
export const runtime = "nodejs";

// The supervisor refreshes updated_at every loop tick (~seconds). Anything older
// than this is STALE -> the stack is not provably running -> never green.
const STALE_SEC = 120;

// Repo root is the webapp's parent dir. The supervisor writes the canonical doc
// to data/frontend/ops/supervisor_status.json relative to the repo root.
const STATUS_PATH = path.join(
  process.cwd(),
  process.cwd().endsWith("webapp") ? ".." : ".",
  "data",
  "frontend",
  "ops",
  "supervisor_status.json",
);

type Proc = {
  name: string;
  state: string;
  pid?: number | null;
  restarts?: number;
  ready?: boolean;
  detail?: { kind?: string; age_sec?: number; fresh_sec?: number; reason?: string };
};

type SupervisorDoc = {
  schema_version?: string;
  profile?: string;
  started_at?: number;
  updated_at?: number;
  all_ready?: boolean;
  procs?: Proc[];
};

// A proc is degraded if it is not READY, or its heartbeat is older than its own
// freshness SLA (a stale heartbeat is a self-heal-in-progress / dead worker).
function procDegraded(p: Proc): boolean {
  if (p.ready === false) return true;
  if (typeof p.state === "string" && p.state.toUpperCase() !== "READY") return true;
  const d = p.detail;
  if (d && typeof d.age_sec === "number" && typeof d.fresh_sec === "number") {
    if (d.age_sec > d.fresh_sec) return true;
  }
  return false;
}

function unavailable(reason: string) {
  // Honest degrade: never green, never a fabricated uptime.
  return NextResponse.json(
    {
      status: "unavailable",
      live: false,
      overall: "down",
      reason,
      all_ready: false,
      procs: [],
      restarts_total: 0,
      uptime_sec: null,
      age_sec: null,
      edge_claimed: false,
    },
    { status: 503 },
  );
}

export async function GET() {
  if (process.env.NEXT_PUBLIC_DATA_MODE === "snapshot") {
    return unavailable("static demo build -- no supervisor process");
  }
  let raw: string;
  try {
    raw = await fs.readFile(STATUS_PATH, "utf-8");
  } catch {
    return unavailable("supervisor_status.json missing or unreadable");
  }

  let doc: SupervisorDoc;
  try {
    doc = JSON.parse(raw) as SupervisorDoc;
  } catch {
    return unavailable("supervisor_status.json torn / not JSON");
  }

  const nowSec = Date.now() / 1000;
  const updated = typeof doc.updated_at === "number" ? doc.updated_at : null;
  const ageSec = updated != null ? Math.max(0, nowSec - updated) : null;

  // STALE feed -> never green. The supervisor is not provably alive.
  if (ageSec == null) {
    return unavailable("supervisor_status.json has no updated_at heartbeat");
  }
  if (ageSec > STALE_SEC) {
    return unavailable(
      `supervisor_status.json stale (${Math.round(ageSec)}s > ${STALE_SEC}s SLA)`,
    );
  }

  const procs = Array.isArray(doc.procs) ? doc.procs : [];
  const anyDegraded = procs.some(procDegraded);
  const allReady = doc.all_ready === true;
  const restartsTotal = procs.reduce(
    (n, p) => n + (typeof p.restarts === "number" ? p.restarts : 0),
    0,
  );
  const uptimeSec =
    typeof doc.started_at === "number" ? Math.max(0, nowSec - doc.started_at) : null;

  // GREEN-CONDITION (the single source of truth for the LIVE badge):
  // fresh feed AND all_ready AND no proc DEGRADED/DOWN. Otherwise honest amber/red.
  const live = allReady && !anyDegraded; // freshness already enforced above
  const overall = live ? "ok" : anyDegraded ? "down" : "degraded";

  return NextResponse.json({
    status: "ok",
    live,
    overall,
    profile: doc.profile ?? null,
    all_ready: allReady,
    any_degraded: anyDegraded,
    n_procs: procs.length,
    restarts_total: restartsTotal,
    uptime_sec: uptimeSec,
    started_at: doc.started_at ?? null,
    updated_at: updated,
    age_sec: ageSec,
    procs: procs.map((p) => ({
      name: p.name,
      state: p.state,
      ready: p.ready ?? null,
      restarts: typeof p.restarts === "number" ? p.restarts : 0,
      degraded: procDegraded(p),
      heartbeat_age_sec: p.detail?.age_sec ?? null,
      heartbeat_fresh_sec: p.detail?.fresh_sec ?? null,
      kind: p.detail?.kind ?? null,
    })),
    edge_claimed: false,
  });
}
