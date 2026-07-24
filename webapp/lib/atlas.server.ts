// atlas.server.ts -- build-time reader for the 7 descriptive-atlas packs.
//
// Mirrors the /receipts + showcase.server pattern: readFileSync of the staged
// public/data/showcase/atlas_*_manifest.json only (no client fetch, no `../`
// traversal into scripts/). Every pack is descriptive_only -- these are
// reference cards (career/last-N summaries), NOT predictions and NOT edge
// claims. The receipt chip each pack/entity carries says so verbatim.
//
// Consumers: PackIndex (/atlas), EntityTable (/atlas/[sport]),
// EntityCard (/atlas/[sport]/[entity]), and the two generateStaticParams.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReceiptChipProps } from "@/lib/showcase.server";

const SHOWCASE_DIR = join(process.cwd(), "public", "data", "showcase");

// The 7 packs, in display order. slug = the /atlas/[sport] route param; file =
// staged manifest basename (a constant, so no path-traversal surface here).
const PACKS = [
  { slug: "nba", label: "NBA players", file: "atlas_nba_manifest" },
  { slug: "nba-teams", label: "NBA teams", file: "atlas_nba_teams_manifest" },
  { slug: "mlb-batters", label: "MLB batters", file: "atlas_mlb_batters_manifest" },
  { slug: "mlb-pitching", label: "MLB pitch types", file: "atlas_mlb_pitch_manifest" },
  { slug: "soccer", label: "Soccer clubs", file: "atlas_soccer_manifest" },
  { slug: "tennis", label: "Tennis players", file: "atlas_tennis_manifest" },
  { slug: "calibration", label: "Calibration segments", file: "atlas_calibration_manifest" },
] as const;

type PackSlug = (typeof PACKS)[number]["slug"];

type RawEntry = {
  entity: string;
  card_path?: string | null;
  key_numbers: Record<string, number | string | Record<string, number>>;
  floors?: string | null;
  as_of?: string | null;
};

type RawManifest = {
  sport?: string;
  descriptive_only?: boolean;
  n_entries?: number;
  generated_at?: string | null;
  entries: RawEntry[];
};

export type PackMeta = {
  slug: PackSlug;
  label: string;
  sport: string;
  count: number;
  asOf: string | null;
  chip: ReceiptChipProps;
};

export type EntityRow = {
  entity: string;
  slug: string;
  nums: Record<string, number | string | Record<string, number>>;
};

export type PackTable = {
  slug: PackSlug;
  label: string;
  sport: string;
  asOf: string | null;
  columns: string[];
  rows: EntityRow[];
  chip: ReceiptChipProps;
};

export type EntityCardProps = {
  slug: string;
  entity: string;
  label: string;
  sport: string;
  keyNumbers: Record<string, number | string | Record<string, number>>;
  floors: string | null;
  asOf: string | null;
  pngHref: string | null;
  chip: ReceiptChipProps;
};

function loadRaw(file: string): RawManifest | null {
  try {
    const raw = JSON.parse(readFileSync(join(SHOWCASE_DIR, `${file}.json`), "utf-8"));
    return Array.isArray(raw?.entries) ? (raw as RawManifest) : null;
  } catch {
    return null;
  }
}

// Stable per-entity slug. Prefer the card_path tail AFTER the pack dir (the
// exporter's own clean names): `.../atlas/nba/nolan_traore.png` -> "nolan_traore",
// `.../atlas/mlb_pitch/by_type/kc.png` -> "by_type_kc". Keeping the subdir is
// load-bearing: mlb_pitch has both by_type/kc and by_team/kc, which collide on
// basename alone. Falls back to a slugified entity name. Always URL-safe.
function entitySlug(e: RawEntry): string {
  const parts = (e.card_path ?? "").replace(/\\/g, "/").split("/").filter(Boolean);
  const ai = parts.indexOf("atlas");
  const tail = ai >= 0 ? parts.slice(ai + 2) : parts.slice(-1);
  const stem = tail.join("_").replace(/\.[a-z0-9]+$/i, "");
  const src = stem || e.entity;
  return src.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function packAsOf(m: RawManifest): string | null {
  return m.entries[0]?.as_of ?? m.generated_at ?? null;
}

// Descriptive-only chip. Cites the staged manifest (clone-safe repo-relative
// path, never a C:/Users path); verified is always descriptive_only for the
// atlas -- these are reference cards, not measured predictions.
function packChip(file: string, asOf: string | null): ReceiptChipProps {
  return {
    sourceArtifact: `webapp/public/data/showcase/${file}.json`,
    asOf,
    verified: "descriptive_only",
    href: null,
  };
}

/** 7-card grid props for /atlas. Skips any pack whose manifest is unstaged. */
export function listPacks(): PackMeta[] {
  const out: PackMeta[] = [];
  for (const p of PACKS) {
    const m = loadRaw(p.file);
    if (!m) continue;
    const asOf = packAsOf(m);
    out.push({
      slug: p.slug,
      label: p.label,
      sport: m.sport ?? p.slug,
      count: m.entries.length,
      asOf,
      chip: packChip(p.file, asOf),
    });
  }
  return out;
}

function packBySlug(slug: string) {
  return PACKS.find((p) => p.slug === slug) ?? null;
}

/** Full sortable table for /atlas/[sport]. Columns = first entry's key_numbers. */
export function getPack(slug: string): PackTable | null {
  const p = packBySlug(slug);
  if (!p) return null;
  const m = loadRaw(p.file);
  if (!m || m.entries.length === 0) return null;
  const columns = Object.keys(m.entries[0].key_numbers);
  const asOf = packAsOf(m);
  return {
    slug: p.slug,
    label: p.label,
    sport: m.sport ?? p.slug,
    asOf,
    columns,
    rows: m.entries.map((e) => ({
      entity: e.entity,
      slug: entitySlug(e),
      nums: e.key_numbers,
    })),
    chip: packChip(p.file, asOf),
  };
}

/** One entity's HTML-card props for /atlas/[sport]/[entity]. */
export function getEntity(slug: string, entity: string): EntityCardProps | null {
  const p = packBySlug(slug);
  if (!p) return null;
  const m = loadRaw(p.file);
  if (!m) return null;
  const e = m.entries.find((x) => entitySlug(x) === entity);
  if (!e) return null;
  const asOf = e.as_of ?? packAsOf(m);
  return {
    slug: entitySlug(e),
    entity: e.entity,
    label: p.label,
    sport: m.sport ?? p.slug,
    keyNumbers: e.key_numbers,
    floors: e.floors ?? null,
    asOf,
    pngHref: e.card_path ? e.card_path.replace(/\\/g, "/") : null,
    chip: packChip(p.file, asOf),
  };
}

/** generateStaticParams for /atlas/[sport] -- one row per staged pack. */
export function packParams(): { sport: PackSlug }[] {
  return listPacks().map((p) => ({ sport: p.slug }));
}

/** generateStaticParams for /atlas/[sport]/[entity] -- all 1,549 entities. */
export function entityParams(): { sport: PackSlug; entity: string }[] {
  const out: { sport: PackSlug; entity: string }[] = [];
  for (const p of PACKS) {
    const m = loadRaw(p.file);
    if (!m) continue;
    for (const e of m.entries) out.push({ sport: p.slug, entity: entitySlug(e) });
  }
  return out;
}
