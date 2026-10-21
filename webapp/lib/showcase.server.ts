// showcase.server.ts -- the single build-time reader for the analytics
// showcase. Every showcase page is a server component that calls these at
// build time; the JSON is staged into webapp/public/data/showcase/*.json by
// scripts/platformkit/analytics_showcase/stage_webapp_assets.py (owned by the
// staging session, NOT this one). Mirrors the /receipts on-disk pattern:
// readFileSync only, no client fetch, no `../` traversal into scripts/.
//
// Fresh-clone honesty: a cited artifact that was never staged returns null and
// the page renders a VALIDATION_PENDING chip -- never a blank, never a made-up
// number. Each artifact self-describes its measurement (source_artifact,
// as_of, method, floors); this reader passes those through untouched so two
// different measurements of the same metric can never be silently paired.

import { readFileSync } from "node:fs";
import { join } from "node:path";

const SHOWCASE_DIR = join(process.cwd(), "public", "data", "showcase");

// An artifact is a staged out/*.json. The header fields below are the ones the
// receipt chip reads; the rest of the payload is page-specific, so we keep an
// open index signature rather than over-typing every exhibit.
export type Artifact = {
  edge_claimed?: boolean;
  descriptive_only?: boolean;
  status?: string | null;
  source_artifact?: string | null;
  source?: string | null;
  as_of?: string | null;
  generated_at?: string | null;
  verdict?: string | null;
  n?: number | null;
  ci?: [number, number] | null;
  stale?: boolean;
  method?: string | null;
  floors?: string | null;
  honest_note?: string | null;
  [key: string]: unknown;
};

export type ModuleMeta = {
  id: string; // out/ basename, the join key
  label: string;
  category?: string;
  source_artifact?: string | null;
  as_of?: string | null;
  descriptive_only?: boolean;
  edge_claimed?: boolean;
  verdict?: string | null;
  status?: string | null;
};

export type SiteManifest = {
  generated_at?: string;
  modules: ModuleMeta[];
};

export type ReceiptChipProps = {
  sourceArtifact: string;
  asOf: string | null;
  verified: "edge_claimed:false" | "descriptive_only" | "validation_pending";
  verdict?: string | null;
  n?: number | null;
  ci?: [number, number] | null;
  stale?: boolean;
  href?: string | null;
};

// ponytail: the id is a URL/route param -- allow only a bare basename so a
// crafted `../../secrets` can never escape the showcase dir. This is the trust
// boundary for the whole reader.
function safeId(id: string): string | null {
  return /^[A-Za-z0-9._-]+$/.test(id) && !id.includes("..") ? id : null;
}

// Not staged (no such file, or a directory where a file was expected) -> null, the
// honest pending chip. Anything else -- a present file that is not valid JSON, a
// permission error -- THROWS: a corrupt artifact must fail the build, never render as
// pending. `dir` overrides the staged directory (tests).
function readJson(basename: string, dir = SHOWCASE_DIR): unknown | null {
  let raw: string;
  try {
    raw = readFileSync(join(dir, basename), "utf-8");
  } catch (e) {
    const code = (e as NodeJS.ErrnoException).code;
    if (code === "ENOENT" || code === "EISDIR" || code === "ENOTDIR") return null;
    throw e;
  }
  try {
    return JSON.parse(raw);
  } catch (e) {
    throw new Error(`showcase: ${join(dir, basename)} is not valid JSON: ${e instanceof Error ? e.message : String(e)}`);
  }
}

// Read one staged artifact by its out/ basename (no .json suffix). Missing or
// unstaged -> null (page renders a pending chip); corrupt -> throws.
export function loadArtifact(id: string, dir = SHOWCASE_DIR): Artifact | null {
  const clean = safeId(id);
  if (!clean) return null;
  return readJson(`${clean}.json`, dir) as Artifact | null;
}

// The T0.1 sample manifest and the static module registry below exist so pages
// compile before the real manifest is staged. They are development scaffolding: a
// production build never ships the sample or the registry in place of the manifest.
const DEV_FALLBACKS = process.env.NODE_ENV !== "production";

// The site index. Prefer the real site_manifest.json; outside production fall back
// to the T0.1 sample. Null-tolerant: callers use listModules().
export function loadManifest(dir = SHOWCASE_DIR): SiteManifest | null {
  const raw = (readJson("site_manifest.json", dir) ??
    (DEV_FALLBACKS ? readJson("manifest-sample.json", dir) : null)) as
    | Partial<SiteManifest>
    | null;
  if (!raw || !Array.isArray(raw.modules)) return null;
  return { generated_at: raw.generated_at, modules: raw.modules };
}

// The showcase modules to render. Manifest rows when present, else a static
// fallback registry keyed to the out/ basenames the pages reference (per
// SITE_PLAN_v2 section 2). Kept minimal on purpose -- the manifest, once
// staged, is the source of truth; this only keeps the site buildable without it.
const FALLBACK_MODULES: ModuleMeta[] = [
  { id: "cross_sport_scoreboard", label: "Cross-sport calibration scoreboard", category: "calibration" },
  { id: "brier_skill_scores", label: "Brier skill scores", category: "calibration" },
  { id: "murphy_decomposition", label: "Murphy decomposition", category: "calibration" },
  { id: "calibration_stability", label: "Calibration stability", category: "calibration" },
  { id: "honesty_exhibit", label: "Honesty exhibit", category: "honesty" },
  { id: "reject_graveyard", label: "Reject graveyard", category: "honesty" },
  { id: "mechanism_survival", label: "Mechanism survival", category: "honesty" },
  { id: "atlas_nba_manifest", label: "NBA players", category: "atlas" },
  { id: "atlas_nba_teams_manifest", label: "NBA teams", category: "atlas" },
  { id: "atlas_mlb_batters_manifest", label: "MLB batters", category: "atlas" },
  { id: "atlas_mlb_pitch_manifest", label: "MLB pitching", category: "atlas" },
  { id: "atlas_calibration_manifest", label: "Calibration", category: "atlas" },
  { id: "atlas_tennis_manifest", label: "Tennis", category: "atlas" },
  { id: "atlas_soccer_manifest", label: "Soccer", category: "atlas" },
  { id: "state_conditioned_calibration", label: "State-conditioned calibration", category: "lab" },
  { id: "market_overreaction", label: "Market overreaction", category: "lab" },
  { id: "tick_microstructure", label: "Tick microstructure", category: "microstructure" },
  { id: "info_arrival_curve", label: "Information-arrival curve", category: "microstructure" },
  { id: "check_all_report", label: "check_all proof harness", category: "methodology" },
];

export function listModules(dir = SHOWCASE_DIR): ModuleMeta[] {
  const m = loadManifest(dir);
  if (m && m.modules.length > 0) return m.modules;
  if (!DEV_FALLBACKS) {
    throw new Error(`showcase: ${join(dir, "site_manifest.json")} is missing or lists no modules; the static registry is development-only`);
  }
  return FALLBACK_MODULES;
}

// Normalize a repo-relative artifact path: Windows backslashes -> forward, no
// leading slash. Absolute paths should already be rewritten by the staging
// task; if one slips through we keep only the repo-relative tail after a
// `nba-ai-system/` marker so no C:/Users path ever renders.
function normPath(p: string | null | undefined): string {
  if (!p) return "";
  const fwd = p.replace(/\\/g, "/");
  const i = fwd.indexOf("nba-ai-system/");
  return i >= 0 ? fwd.slice(i + "nba-ai-system/".length) : fwd;
}

// Map an artifact or module header into the receipt chip props. verified is
// derived from the honesty header the artifacts already carry:
//   descriptive_only:true  -> descriptive_only (atlas/descriptive surfaces)
//   edge_claimed:false     -> edge_claimed:false (measured, no $ claimed)
//   neither / null artifact -> validation_pending (fresh clone, missing file)
export function receiptChip(a: Artifact | ModuleMeta | null): ReceiptChipProps {
  if (!a) {
    return { sourceArtifact: "", asOf: null, verified: "validation_pending" };
  }
  const source =
    (a as Artifact).source_artifact ??
    (a as Artifact).source ??
    (a as ModuleMeta).source_artifact ??
    null;
  const asOf =
    (a.as_of as string | null | undefined) ??
    ((a as Artifact).generated_at as string | null | undefined) ??
    null;

  let verified: ReceiptChipProps["verified"];
  if (a.descriptive_only === true) verified = "descriptive_only";
  else if (a.edge_claimed === false) verified = "edge_claimed:false";
  else verified = "validation_pending";

  return {
    sourceArtifact: normPath(source),
    asOf: asOf ?? null,
    verified,
    verdict: (a.verdict as string | null | undefined) ?? null,
    n: (a as Artifact).n ?? null,
    ci: (a as Artifact).ci ?? null,
    stale: (a as Artifact).stale ?? false,
    href: null,
  };
}
