#!/usr/bin/env node
// gen-figures.mjs -- generates webapp/lib/figures.ts from docs/evidence/CANONICAL_FIGURES.json.
//
// The JSON (read by scripts/platformkit/eval_gate/claim_consistency.py) is the single
// canonical set of public figures: build-volume counts, the forward window, the G6
// status and every pregame-vs-close / in-game-vs-market row. This script turns it into
// typed constants so a page can render a figure only BY KEY (components/evidence/
// FigureValue.tsx) and a figure, its as-of date and its source path cannot drift from
// the packet. It fails loudly when the JSON is missing or malformed.
//
// Usage:
//   node scripts/gen-figures.mjs            write lib/figures.ts (npm run build runs this)
//   node scripts/gen-figures.mjs --check    exit 1 when lib/figures.ts is stale
//   node scripts/gen-figures.mjs --stdout   print the module instead of writing it
//   --in <path> / --out <path>              override the JSON / module paths (tests)
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const WEBAPP_ROOT = resolve(HERE, "..");
export const REPO_ROOT = resolve(WEBAPP_ROOT, "..");
export const FIGURES_JSON = "docs/evidence/CANONICAL_FIGURES.json";
export const DEFAULT_IN = resolve(REPO_ROOT, FIGURES_JSON);
export const DEFAULT_OUT = resolve(WEBAPP_ROOT, "lib", "figures.ts");
export const SCHEMA = "canonical_figures/v1";

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const KEY = /^[a-z][a-z0-9_]*$/;
// Regex / audit-only fields of the JSON that a page never renders.
const COUNT_DROP = new Set(["pattern", "unless", "unless_why", "forbidden"]);
const FIGURE_DROP = new Set(["anchor", "also_ci95", "also_ci95_why"]);

export class FiguresError extends Error {}

function fail(message) {
  throw new FiguresError(`gen-figures: ${message}`);
}

function requireString(obj, field, where) {
  if (typeof obj[field] !== "string" || obj[field].trim() === "") fail(`${where}: "${field}" must be a non-empty string`);
}

function requireDay(obj, field, where) {
  requireString(obj, field, where);
  if (!ISO_DAY.test(obj[field])) fail(`${where}: "${field}" must be an ISO day (YYYY-MM-DD), got "${obj[field]}"`);
}

function checkKey(entry, where, seen) {
  if (typeof entry.key !== "string" || !KEY.test(entry.key)) fail(`${where}: "key" must be snake_case, got ${JSON.stringify(entry.key)}`);
  if (seen.has(entry.key)) fail(`${where}: duplicate key "${entry.key}"`);
  seen.add(entry.key);
}

function pick(entry, drop) {
  return Object.fromEntries(Object.entries(entry).filter(([field]) => !drop.has(field)));
}

/** Validates the parsed JSON and returns the normalized figure sets the module is built from. */
export function normalize(cfg, label = FIGURES_JSON) {
  if (!cfg || typeof cfg !== "object" || Array.isArray(cfg)) fail(`${label}: top level must be an object`);
  if (cfg.schema !== SCHEMA) fail(`${label}: schema must be "${SCHEMA}", got ${JSON.stringify(cfg.schema)}`);
  requireDay(cfg, "as_of", label);
  const counts = cfg.canonical_counts?.figures;
  if (!Array.isArray(counts) || counts.length === 0) fail(`${label}: canonical_counts.figures must be a non-empty array`);
  if (!Array.isArray(cfg.figures) || cfg.figures.length === 0) fail(`${label}: figures must be a non-empty array`);
  const seen = new Set();
  const countFigures = {};
  for (const [index, entry] of counts.entries()) {
    const where = `${label}: canonical_counts.figures[${index}]`;
    checkKey(entry, where, seen);
    if (!(typeof entry.value === "number" && Number.isFinite(entry.value)) && typeof entry.value !== "string") {
      fail(`${where}: "value" must be a finite number or a string`);
    }
    requireDay(entry, "as_of", where);
    requireString(entry, "source", where);
    const historical = Array.isArray(entry.historical)
      ? entry.historical.map((h) => ({ value: h.value, as_of: h.as_of, source: h.source }))
      : undefined;
    countFigures[entry.key] = { kind: "count", ...pick(entry, COUNT_DROP), ...(historical ? { historical } : {}) };
  }
  const comparisonFigures = {};
  for (const [index, entry] of cfg.figures.entries()) {
    const where = `${label}: figures[${index}]`;
    checkKey(entry, where, seen);
    requireString(entry, "verdict", where);
    requireDay(entry, "as_of", where);
    requireString(entry, "source", where);
    requireString(entry, "licenses", where);
    for (const field of ["n", "model", "close", "gap", "mde"]) {
      if (entry[field] !== undefined && !(typeof entry[field] === "number" && Number.isFinite(entry[field]))) {
        fail(`${where}: "${field}" must be a finite number when present`);
      }
    }
    comparisonFigures[entry.key] = { kind: "comparison", ...pick(entry, FIGURE_DROP) };
  }
  const retracted = Array.isArray(cfg.retracted_tokens) ? cfg.retracted_tokens : [];
  if (!retracted.every((token) => typeof token === "string")) fail(`${label}: retracted_tokens must be strings`);
  return { asOf: cfg.as_of, retracted, countFigures, comparisonFigures };
}

const literal = (value) => JSON.stringify(value, null, 2);

/** Renders the TypeScript module for a validated figure set. */
export function generate(cfg, label = FIGURES_JSON) {
  const { asOf, retracted, countFigures, comparisonFigures } = normalize(cfg, label);
  return `// GENERATED by webapp/scripts/gen-figures.mjs from ${FIGURES_JSON}.
// DO NOT EDIT. Edit the JSON (the canonical set claim_consistency.py checks) and run
// \`npm run gen:figures\`; \`npm run build\` regenerates it, and lib/figures.test.ts fails
// when this committed copy is stale. Pages render these only through
// components/evidence/FigureValue.tsx, never by retyping a number.
/* eslint-disable */

/** Repo-relative path of the canonical figure set. */
export const FIGURES_SOURCE = ${literal(FIGURES_JSON)} as const;
export const FIGURES_SCHEMA = ${literal(SCHEMA)} as const;
/** Top-level as_of of the canonical set (the pregame figures' corrected date). */
export const FIGURES_AS_OF = ${literal(asOf)} as const;
/** Retracted figures; never rendered as current anywhere on the site. */
export const RETRACTED_TOKENS = ${literal(retracted)} as const;

/** Build-volume, site-size, forward-window and G6-status figures. */
export const COUNT_FIGURES = ${literal(countFigures)} as const;

/** Pregame-vs-close and in-game-vs-market rows with the packet's verdict labels. */
export const COMPARISON_FIGURES = ${literal(comparisonFigures)} as const;

export const FIGURES = { ...COUNT_FIGURES, ...COMPARISON_FIGURES } as const;

export type CountFigureKey = keyof typeof COUNT_FIGURES;
export type ComparisonFigureKey = keyof typeof COMPARISON_FIGURES;
export type FigureKey = CountFigureKey | ComparisonFigureKey;
export type CountFigure = (typeof COUNT_FIGURES)[CountFigureKey];
export type ComparisonFigure = (typeof COMPARISON_FIGURES)[ComparisonFigureKey];
export type CanonicalFigure = (typeof FIGURES)[FigureKey];

export const FIGURE_KEYS = Object.keys(FIGURES) as FigureKey[];

export function isFigureKey(key: unknown): key is FigureKey {
  return typeof key === "string" && Object.prototype.hasOwnProperty.call(FIGURES, key);
}

export function isComparisonFigureKey(key: unknown): key is ComparisonFigureKey {
  return typeof key === "string" && Object.prototype.hasOwnProperty.call(COMPARISON_FIGURES, key);
}

export function figure<K extends FigureKey>(key: K): (typeof FIGURES)[K] {
  return FIGURES[key];
}
`;
}

/** Reads the JSON at inPath and returns the generated module text; throws FiguresError when it is missing. */
export function generateFromFile(inPath = DEFAULT_IN) {
  const label = relative(REPO_ROOT, inPath) || inPath;
  if (!existsSync(inPath)) {
    fail(`${label} is missing. The canonical figure set lives at ${FIGURES_JSON} in the repo root; ` +
      "the webapp build cannot proceed without it.");
  }
  let parsed;
  try {
    parsed = JSON.parse(readFileSync(inPath, "utf8"));
  } catch (error) {
    fail(`${label} is not valid JSON: ${error instanceof Error ? error.message : String(error)}`);
  }
  return generate(parsed, label);
}

function parseArgs(argv) {
  const args = { in: DEFAULT_IN, out: DEFAULT_OUT, check: false, stdout: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--check") args.check = true;
    else if (arg === "--stdout") args.stdout = true;
    else if ((arg === "--in" || arg === "--out") && argv[index + 1]) args[arg.slice(2)] = resolve(argv[++index]);
    else fail(`unknown argument ${arg}`);
  }
  return args;
}

export function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const text = generateFromFile(args.in);
  if (args.stdout) {
    process.stdout.write(text);
    return 0;
  }
  const outLabel = relative(WEBAPP_ROOT, args.out) || args.out;
  if (args.check) {
    const current = existsSync(args.out) ? readFileSync(args.out, "utf8").replace(/\r\n/g, "\n") : null; // ponytail: autocrlf checkouts
    if (current !== text) {
      console.error(`gen-figures: ${outLabel} is stale against ${relative(REPO_ROOT, args.in)}; run \`npm run gen:figures\`.`);
      return 1;
    }
    console.log(`gen-figures: ${outLabel} matches the canonical set.`);
    return 0;
  }
  writeFileSync(args.out, text);
  const { countFigures, comparisonFigures } = normalize(JSON.parse(readFileSync(args.in, "utf8")));
  console.log(`gen-figures: wrote ${outLabel} (${Object.keys(countFigures).length} count + ` +
    `${Object.keys(comparisonFigures).length} comparison figures from ${relative(REPO_ROOT, args.in)}).`);
  return 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    process.exit(main());
  } catch (error) {
    console.error(error instanceof FiguresError ? error.message : error);
    process.exit(1);
  }
}
