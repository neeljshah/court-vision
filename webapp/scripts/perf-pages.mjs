// perf-pages.mjs -- shared page-list helpers for the perf budget and the a11y gate.
import { readFileSync } from "node:fs";

/**
 * Expands "manifest:<key>:<index>" entries into the exported page path, using the
 * baked demo manifest (webapp/public/demo-data/manifest.json). Paper trade ids are
 * percent-encoded twice, exactly as lib/paperLinks.ts builds the site's own hrefs:
 * the export writes the encoded id as the directory name and the host decodes once.
 * Plain paths pass through; an unresolvable entry returns null.
 */
export function resolvePage(entry, manifest) {
  if (typeof entry !== "string" || !entry.startsWith("manifest:")) return entry;
  const [, key, index] = entry.split(":");
  const list = manifest && Array.isArray(manifest[key]) ? manifest[key] : [];
  const id = list[Number(index) || 0];
  if (typeof id !== "string") return null;
  if (key === "bet_ids") return `/paper/${encodeURIComponent(id).replace(/\./g, "%2E")}/`;
  return null;
}

/** The baked demo manifest, or null outside snapshot mode. */
export function readManifest(path = "public/demo-data/manifest.json") {
  try { return JSON.parse(readFileSync(path, "utf8")); } catch { return null; }
}
