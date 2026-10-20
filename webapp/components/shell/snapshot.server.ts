// components/shell/snapshot.server.ts -- the two snapshot dates the banner and footer
// print (moved from the old terminal layout): model data as of = demo-data manifest
// generated_at; paper desk record through = desk latest.json date. Build-time only.
// ponytail: a missing or unreadable file omits that date rather than failing the build.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { isSnapshotMode } from "@/lib/fetchHonest";
import { loadDesk } from "@/lib/desk.server";

export type SnapshotDates = { modelAsOf: string | null; deskThrough: string | null };

const day = (v: unknown): string | null =>
  typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v) ? v.slice(0, 10) : null;

export function snapshotDates(): SnapshotDates {
  if (!isSnapshotMode) return { modelAsOf: null, deskThrough: null };
  let modelAsOf: string | null = null;
  try {
    const m = JSON.parse(readFileSync(join(process.cwd(), "public/demo-data/manifest.json"), "utf-8"));
    modelAsOf = day(m?.generated_at);
  } catch {
    modelAsOf = null;
  }
  let deskThrough: string | null = null;
  try {
    deskThrough = day(loadDesk()?.date);
  } catch {
    deskThrough = null;
  }
  return { modelAsOf, deskThrough };
}

/** "model data as of 2026-07-16; paper desk record through 2026-10-16" (parts omitted when unknown). */
export function snapshotLine(d: SnapshotDates): string | null {
  const parts = [
    d.modelAsOf ? `model data as of ${d.modelAsOf}` : null,
    d.deskThrough ? `paper desk record through ${d.deskThrough}` : null,
  ].filter(Boolean);
  return parts.length ? parts.join("; ") : null;
}
