// system/funnel-artifacts/route.ts -- page-local SERVER route that reads the
// on-disk gate-verdict artifacts (data/frontend/funnel/*.json) + the improvement
// backlog (.planning/product/meta/improvement_backlog.json) and normalizes them
// into a rich, sortable ledger the System page can render WITHOUT touching the
// frozen shared client (@/lib/api) or any live API service.
//
// HONESTY RAILS: this route only READS local artifacts written by the leak-free
// gate -- it never computes, ranks, or fabricates a verdict. Every row is a
// CALIBRATION verdict; vs_close stays UNPROVEN; there is NO $/ROI/payout field.
// If an artifact is missing/garbled it is simply omitted (honest-empty), never
// green-on-missing. Owned by the System lane (app/system/*).

import { NextResponse } from "next/server";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

// Snapshot demo build (output:'export') can't ship a force-dynamic route.
// systemApi.ts's getLocalJson degrades to Unavailable on any non-2xx/network
// error already, so the System page's rich ledger/backlog panels just show
// honest "unavailable" in the demo -- no live artifact reads there anyway.
export const dynamic =
  process.env.NEXT_PUBLIC_DATA_MODE === "snapshot" ? "force-static" : "force-dynamic";

// data/ lives two levels up from webapp/ (repo root). cwd is the webapp dir.
const REPO_ROOT = path.resolve(process.cwd(), "..");
const FUNNEL_DIR = path.join(REPO_ROOT, "data", "frontend", "funnel");
const BACKLOG_PATH = path.join(
  REPO_ROOT,
  ".planning",
  "product",
  "meta",
  "improvement_backlog.json",
);

interface LedgerRow {
  id: string;
  sport: string;
  layer: string;
  verdict: string; // SHIP | REJECT | PARTIAL | TIER3_BLOCKED | INSUFFICIENT_DATA | COHERENCE
  deciding_stat: string; // the leak-free DM / Brier figure that decided it
  corpora: number; // n independent corpora the gate replicated across
  vs_close: string; // always UNPROVEN where no in-play odds exist
  base: string; // the proven base model the candidate had to beat
  source: string; // artifact filename
}

const NUM = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;
const STR = (v: unknown): string => (typeof v === "string" ? v : "");

function inferSport(layer: string, file: string): string {
  const s = `${layer} ${file}`.toLowerCase();
  if (s.includes("soccer_intl")) return "soccer_intl";
  if (s.includes("soccer")) return "soccer";
  if (s.includes("tennis")) return "tennis";
  if (s.includes("mlb")) return "mlb";
  if (s.includes("nba") || s.includes("possession") || s.includes("travel"))
    return "nba";
  return "platform";
}

// Pull the single most-deciding leak-free figure (clustered-DM p or Brier delta)
// from whatever nested shape the artifact uses. Pure read; never invented.
function decidingStat(d: Record<string, unknown>): string {
  const pick = (o: unknown): { dm_p?: number; delta?: number } | null => {
    if (!o || typeof o !== "object") return null;
    const r = o as Record<string, unknown>;
    const dm_p = NUM(r.dm_p);
    const delta = NUM(r.brier_delta);
    if (dm_p == null && delta == null) return null;
    return { dm_p: dm_p ?? undefined, delta: delta ?? undefined };
  };
  // Prefer the SHIP/strongest result row, else first column, else corpus blocks.
  const results = Array.isArray(d.results) ? (d.results as unknown[]) : [];
  let best: { dm_p?: number; delta?: number } | null = null;
  for (const r of results) {
    const ca = pick((r as Record<string, unknown>).corpus_a) || pick(r);
    if (ca && (best == null || (ca.dm_p ?? 1) < (best.dm_p ?? 1))) best = ca;
  }
  best =
    best ||
    pick((d.null as Record<string, unknown>)?.corpus_a) ||
    pick((d.layer_result as Record<string, unknown>)?.a_to_b) ||
    pick(d.layer_result) ||
    null;
  if (best) {
    const parts: string[] = [];
    if (best.dm_p != null) parts.push(`clustered-DM p ~= ${best.dm_p.toFixed(4)}`);
    if (best.delta != null)
      parts.push(`Brier delta ${best.delta >= 0 ? "+" : ""}${best.delta.toFixed(4)}`);
    if (parts.length) return parts.join(", ");
  }
  const reason = STR(d.reason) || STR((d.acquisition as Record<string, unknown>)?.reason);
  if (reason) return reason.slice(0, 160);
  return "held-out Brier verdict (see artifact)";
}

function normVerdict(v: string): string {
  const u = v.toUpperCase();
  if (["SHIP", "PROMOTE", "REJECT", "PARTIAL", "TIER3_BLOCKED", "INSUFFICIENT_DATA"].includes(u))
    return u;
  if (u.startsWith("GREEN")) return "COHERENCE";
  if (u === "COHERENCE") return "COHERENCE";
  return u || "REJECT";
}

function artifactToRows(file: string, d: Record<string, unknown>): LedgerRow[] {
  // soccer_redcard stores the string layer under real_layer (layer is a dict).
  const layerRaw =
    typeof d.layer === "string"
      ? (d.layer as string)
      : STR(d.real_layer) || STR((d.layer as Record<string, unknown>)?.layer) || file.replace(/\.json$/, "");
  const sport = inferSport(layerRaw, file);
  const vsClose = STR(d.vs_close) || "UNPROVEN -- CALIBRATION only, not a market edge";
  const base = STR(d.base) || STR(d.base_model) || STR(d.champion) || STR(d.design) || "";
  const corpora = NUM(d.n_corpora) ?? 0;

  // soccer corners artifact: emit per-column rows so the lone SHIP is visible.
  const results = Array.isArray(d.results) ? (d.results as Record<string, unknown>[]) : [];
  const perColumn = results.filter((r) => STR(r.column) && STR(r.verdict));
  if (perColumn.length) {
    return perColumn.map((r) => {
      const ca = (r.corpus_a as Record<string, unknown>) || {};
      const dm = NUM(ca.dm_p);
      const delta = NUM(ca.brier_delta);
      const stat = [
        dm != null ? `clustered-DM p ~= ${dm.toFixed(4)}` : null,
        delta != null ? `Brier delta ${delta >= 0 ? "+" : ""}${delta.toFixed(4)}` : null,
      ]
        .filter(Boolean)
        .join(", ") || "held-out Brier verdict";
      return {
        id: `${file}:${STR(r.column)}`,
        sport,
        layer: `${layerRaw} [${STR(r.column)}]`,
        verdict: normVerdict(STR(r.verdict)),
        deciding_stat: stat,
        corpora,
        vs_close: vsClose,
        base,
        source: file,
      };
    });
  }

  return [
    {
      id: file,
      sport,
      layer: layerRaw,
      verdict: normVerdict(STR(d.verdict) || STR(d.status)),
      deciding_stat: decidingStat(d),
      corpora,
      vs_close: vsClose,
      base,
      source: file,
    },
  ];
}

async function loadLedger(): Promise<{ rows: LedgerRow[]; counts: Record<string, number> }> {
  let files: string[] = [];
  try {
    files = (await readdir(FUNNEL_DIR)).filter((f) => f.endsWith(".json"));
  } catch {
    return { rows: [], counts: {} };
  }
  const rows: LedgerRow[] = [];
  for (const f of files) {
    if (f.includes("parity") || f.includes("coherence")) continue; // not gate verdicts
    try {
      const raw = await readFile(path.join(FUNNEL_DIR, f), "utf8");
      const d = JSON.parse(raw) as Record<string, unknown>;
      rows.push(...artifactToRows(f, d));
    } catch {
      // garbled artifact -> omit (honest-empty), never fabricate a row.
    }
  }
  const counts: Record<string, number> = {};
  for (const r of rows) counts[r.verdict] = (counts[r.verdict] || 0) + 1;
  return { rows, counts };
}

async function loadBacklog(): Promise<Record<string, unknown> | null> {
  try {
    const raw = await readFile(BACKLOG_PATH, "utf8");
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return null;
  }
}

export async function GET() {
  const [ledger, backlog] = await Promise.all([loadLedger(), loadBacklog()]);
  return NextResponse.json(
    {
      status: "ok",
      ledger,
      backlog,
      edge_claimed: false,
      honest_note:
        "Every row is a CALIBRATION verdict from the leak-free gate. A REJECT is " +
        "a SUCCESS (markets are efficient). The lone SHIP (soccer corners) is a " +
        "calibration survivor, not a market edge -- vs_close is UNPROVEN. No $.",
    },
    { headers: { "cache-control": "no-store" } },
  );
}
