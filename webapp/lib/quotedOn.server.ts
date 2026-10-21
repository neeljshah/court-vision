// quotedOn.server.ts -- the build-time "quoted on" generator (DESIGN_BRIEF section 3 interlinking
// contract): for a receipt's source artifact, list every static route and every docs/papers readout
// that quotes it. A text quotes an artifact when it names the full basename with its extension, or
// the stem as a whole word when the stem is identifier-shaped (an underscore, or letters mixed with
// digits or hyphens: bookmaker_accuracy, DM_RECOMPUTE_2026-09-24). A bare-word stem such as "latest"
// or a date-only stem counts only with its extension, so prose never produces a quote.
// A route's text is its page.tsx plus the modules it imports directly through "@/". Both corpora
// (routes, papers) are read once per build.
// ponytail: text match, one import level deep; the ceiling is a page that reaches the artifact
// through two hops of helpers. Upgrade path: a manifest written by the loaders.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

export type QuotedOn = { label: string; href: string };

const ROOT = process.cwd();
const APP = join(ROOT, "app");
const PAPERS_DIR = join(ROOT, "..", "docs", "papers");
const PAPERS_BLOB = "https://github.com/neeljshah/court-vision/blob/master/docs/papers/";

function pages(dir = APP, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "__tests__" || name.startsWith("[")) continue; // ponytail: dynamic routes skipped
    const p = join(dir, name);
    if (statSync(p).isDirectory()) pages(p, out);
    else if (name === "page.tsx") out.push(p);
  }
  return out;
}

/** app/(group)/a/b/page.tsx -> /a/b/ (route groups dropped). */
export function routeFor(pageFile: string): string {
  const parts = relative(APP, pageFile).split(sep).slice(0, -1).filter((s) => !/^\(.*\)$/.test(s));
  return parts.length ? `/${parts.join("/")}/` : "/";
}

function resolveImport(spec: string): string | null {
  const base = join(ROOT, spec.replace(/^@\//, ""));
  for (const ext of [".ts", ".tsx", ".server.ts", "/index.ts", "/index.tsx"]) if (existsSync(base + ext)) return base + ext;
  return existsSync(base) && statSync(base).isFile() ? base : null;
}

type RouteText = { route: string; text: string };
let routeCorpus: RouteText[] | null = null;
/** Every static route with its page source and one level of "@/" imports; read once per build. */
export function routeTexts(): RouteText[] {
  if (routeCorpus) return routeCorpus;
  routeCorpus = pages().map((file) => {
    const src = readFileSync(file, "utf-8");
    const deps = [...src.matchAll(/from\s+"(@\/[^"]+)"/g)].map((m) => resolveImport(m[1])).filter((f): f is string => !!f);
    return { route: routeFor(file), text: [src, ...deps.map((d) => readFileSync(d, "utf-8"))].join("\n") };
  });
  return routeCorpus;
}

type PaperText = { file: string; text: string };
const paperCorpus = new Map<string, PaperText[]>();
/** docs/papers/*.md with their text; read once per directory per build. */
function paperTexts(dir: string): PaperText[] {
  const hit = paperCorpus.get(dir);
  if (hit) return hit;
  const out = existsSync(dir)
    ? readdirSync(dir).filter((f) => f.endsWith(".md")).sort().map((f) => ({ file: f, text: readFileSync(join(dir, f), "utf-8") }))
    : [];
  paperCorpus.set(dir, out);
  return out;
}

const WORD = "[A-Za-z0-9_-]";
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const identifierShaped = (stem: string) => stem.includes("_") || (/[A-Za-z]/.test(stem) && /[0-9-]/.test(stem));

/** The pattern a text must contain to quote the artifact (null for an empty name). */
export function quotePattern(artifact: string): RegExp | null {
  const base = artifact.replace(/\\/g, "/").split("/").pop() ?? "";
  const stem = base.replace(/\.(json|md|jsonl)$/, "");
  if (!stem) return null;
  const alts = [escapeRe(base)];
  if (stem !== base && identifierShaped(stem)) alts.push(escapeRe(stem));
  return new RegExp(`(?<!${WORD})(?:${alts.join("|")})(?!${WORD})`);
}

/** True when `text` names the artifact by the rule above. */
export const quotes = (text: string, artifact: string): boolean => quotePattern(artifact)?.test(text) ?? false;

export function quotedOn(artifact: string, papersDir = PAPERS_DIR): QuotedOn[] {
  const re = quotePattern(artifact);
  if (!re) return [];
  const routes = routeTexts().filter((r) => re.test(r.text)).map((r) => ({ label: r.route, href: r.route }));
  const papers = paperTexts(papersDir).filter((p) => re.test(p.text))
    .map((p) => ({ label: `docs/papers/${p.file}`, href: `${PAPERS_BLOB}${p.file}` }));
  return [...routes.sort((a, b) => a.href.localeCompare(b.href)), ...papers];
}
