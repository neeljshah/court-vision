#!/usr/bin/env node
// Check committed or exported analytics data with the same JSON parser as browsers.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const defaultRoot = resolve(here, "..", "public", "data");

function hasNonFiniteNumber(value) {
  if (typeof value === "number") return !Number.isFinite(value);
  if (value && typeof value === "object") return Object.values(value).some(hasNonFiniteNumber);
  return false;
}

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

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = verifyPublicJson(process.argv[2] ? resolve(process.argv[2]) : defaultRoot);
  console.log(`Public JSON scan: ${result.fileCount} files, ${result.failures.length} failures.`);
  for (const failure of result.failures) console.error(failure);
  process.exitCode = result.failures.length ? 1 : 0;
}
