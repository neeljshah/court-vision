#!/usr/bin/env node
// Fails when a "use client" component can reach a module that imports node:fs / node:path.
// `next dev`, vitest and tsc all pass in that situation; only the static `next build` fails
// ("UnhandledSchemeError: Reading from node:fs"). This runs in well under a second.
// Usage: node scripts/check-client-imports.mjs   (exit 1 with the offending chains)
import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join, dirname, resolve, relative } from "node:path";

const ROOT = process.cwd();
const SCAN_DIRS = ["app", "components", "lib"];
const NODE_ONLY = /from\s+["'](node:fs|fs|node:path|path|node:fs\/promises|fs\/promises)["']/;
// `import type` / `export type` are erased by the compiler and never reach webpack.
const IMPORT_RE = /(?:import|export)(?!\s+type\s)\s[^"'\n]*?from\s+["']([^"']+)["']|import\s*\(\s*["']([^"']+)["']\s*\)/g;
const EXTS = [".ts", ".tsx", ".js", ".mjs"];

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (name === "node_modules" || name.startsWith(".")) continue;
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(ts|tsx|js|mjs)$/.test(name) && !/\.test\.|\.spec\./.test(name)) out.push(full);
  }
  return out;
}

function resolveImport(fromFile, spec) {
  let base;
  if (spec.startsWith("@/")) base = join(ROOT, spec.slice(2));
  else if (spec.startsWith(".")) base = resolve(dirname(fromFile), spec);
  else return null; // package import
  for (const candidate of [base, ...EXTS.map((ext) => base + ext), ...EXTS.map((ext) => join(base, "index" + ext))]) {
    if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  }
  return null;
}

const files = SCAN_DIRS.filter((dir) => existsSync(join(ROOT, dir))).flatMap((dir) => walk(join(ROOT, dir)));
const source = new Map(files.map((file) => [file, readFileSync(file, "utf8")]));
const edges = new Map();
for (const [file, text] of source) {
  const targets = [];
  for (const match of text.matchAll(IMPORT_RE)) {
    const target = resolveImport(file, match[1] || match[2]);
    if (target && source.has(target)) targets.push(target);
  }
  edges.set(file, targets);
}
const nodeOnly = new Set([...source].filter(([, text]) => NODE_ONLY.test(text)).map(([file]) => file));
const clientFiles = [...source].filter(([, text]) => /^\s*["']use client["']/m.test(text)).map(([file]) => file);

const failures = [];
for (const start of clientFiles) {
  const parent = new Map([[start, null]]);
  const queue = [start];
  while (queue.length) {
    const file = queue.shift();
    if (nodeOnly.has(file)) {
      const chain = [];
      for (let cursor = file; cursor; cursor = parent.get(cursor)) chain.unshift(relative(ROOT, cursor));
      failures.push(chain.join(" -> "));
      break;
    }
    for (const next of edges.get(file) || []) {
      if (!parent.has(next)) { parent.set(next, file); queue.push(next); }
    }
  }
}

// Second trap: Next's build-time type check rejects any value export from a page/layout module
// other than the documented ones ("Property 'X' is incompatible with index signature").
const PAGE_EXPORTS = new Set(["default", "metadata", "generateMetadata", "generateStaticParams", "dynamic", "dynamicParams",
  "revalidate", "fetchCache", "runtime", "preferredRegion", "maxDuration", "viewport", "generateViewport", "config"]);
const strayExports = [];
for (const [file, text] of source) {
  if (!/[\\/]app[\\/].*[\\/](page|layout|template|error|loading|not-found)\.(tsx|ts|js)$/.test(file)) continue;
  for (const match of text.matchAll(/^export\s+(?:const|let|var|function|class|async function)\s+([A-Za-z_$][\w$]*)/gm)) {
    if (!PAGE_EXPORTS.has(match[1])) strayExports.push(`${relative(ROOT, file)} exports ${match[1]}`);
  }
}

if (failures.length || strayExports.length) {
  if (failures.length) {
    console.log(`FAIL client components reach node-only modules (${failures.length}):`);
    for (const chain of failures) console.log("  " + chain);
  }
  if (strayExports.length) {
    console.log(`FAIL page/layout modules with non-standard exports (${strayExports.length}) -- move them to a sibling module:`);
    for (const line of strayExports) console.log("  " + line);
  }
  process.exit(1);
}
console.log(`OK ${clientFiles.length} client components, ${nodeOnly.size} node-only modules, no client chain reaches node:fs/node:path, no stray page exports`);
