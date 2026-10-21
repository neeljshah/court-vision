#!/usr/bin/env node
// Check committed or exported analytics data with the same JSON parser as browsers, then
// apply the per-artifact key/type rules and the snapshot-completeness check
// (scripts/verify-public-rules.mjs). Wired into `npm run build` through the prebuild
// script, so a corrupt, non-finite, mis-shaped or missing artifact fails CI loudly.
//
//   node scripts/verify-public-json.mjs            the site gate (public/data + public/demo-data + the rules)
//   node scripts/verify-public-json.mjs <dir>      the generic parse / non-finite scan of one directory
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { runArtifactRules } from "./verify-public-rules.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const defaultWebappRoot = resolve(here, "..");
const defaultRoot = resolve(defaultWebappRoot, "public", "data");

function hasNonFiniteNumber(value) {
  if (typeof value === "number") return !Number.isFinite(value);
  if (value && typeof value === "object") return Object.values(value).some(hasNonFiniteNumber);
  return false;
}

/** Generic scan: every *.json under root parses and holds no non-finite number. */
export function verifyPublicJson(root = defaultRoot) {
  const failures = [];
  let fileCount = 0;
  function visit(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const file = join(directory, entry.name);
      if (entry.isDirectory()) visit(file);
      else if (entry.isFile() && entry.name.endsWith(".json")) {
        fileCount += 1;
        const label = relative(root, file).replaceAll("\\", "/");
        try {
          const value = JSON.parse(readFileSync(file, "utf8"));
          if (hasNonFiniteNumber(value)) failures.push(`${label}: non-finite numeric value`);
        } catch {
          failures.push(`${label}: invalid or unreadable JSON`);
        }
      }
    }
  }
  try { visit(root); }
  catch { failures.push("Public data directory is unavailable or unreadable."); }
  if (!fileCount) failures.push("No public JSON files found.");
  return { fileCount, failures };
}

/**
 * The site gate: the generic scan over public/data (always) and public/demo-data (required
 * in a snapshot build, scanned when present otherwise), then the artifact rules.
 */
export function verifySite({ webappRoot = defaultWebappRoot, repoRoot = resolve(webappRoot, ".."), snapshot = false } = {}) {
  const failures = [];
  const scan = (rel, required) => {
    const dir = join(webappRoot, rel);
    if (!existsSync(dir)) {
      if (required) failures.push(`${rel}: missing; a snapshot build has no data source without the export.`);
      return 0;
    }
    const result = verifyPublicJson(dir);
    failures.push(...result.failures.map((f) => `${rel}: ${f}`));
    return result.fileCount;
  };
  const fileCount = scan("public/data", true) + scan("public/demo-data", snapshot);
  const rules = runArtifactRules({ webappRoot, repoRoot, snapshot });
  return { fileCount, checked: rules.checked, failures: [...failures, ...rules.failures] };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const target = process.argv[2];
  const snapshot = process.env.NEXT_PUBLIC_DATA_MODE === "snapshot";
  const result = target ? verifyPublicJson(resolve(target)) : verifySite({ snapshot });
  const scope = target ? resolve(target) : `site gate, snapshot completeness ${snapshot ? "required" : "checked where the export is present"}`;
  console.log(`Public JSON scan (${scope}): ${result.fileCount} files, ${result.checked ?? 0} artifact rules, ${result.failures.length} failures.`);
  for (const failure of result.failures) console.error(failure);
  process.exitCode = result.failures.length ? 1 : 0;
}
