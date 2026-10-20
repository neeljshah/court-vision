// quotedOn.server.ts -- the build-time "quoted on" generator (DESIGN_BRIEF section 3 interlinking
// contract): for a receipt's source artifact, list every static route and every docs/papers readout
// that quotes it. A route quotes an artifact when its page.tsx, or a module that page imports
// directly through "@/", names the artifact's basename (with or without extension).
// ponytail: text match on basename, one import level deep; the ceiling is a page that reaches the
// artifact through two hops of helpers. Upgrade path: a manifest written by the loaders.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

export type QuotedOn = { label: string; href: string };

const ROOT = process.cwd();
const APP = join(ROOT, "app");

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

let corpus: { route: string; text: string }[] | null = null;
function routeTexts() {
  if (corpus) return corpus;
  corpus = pages().map((file) => {
    const src = readFileSync(file, "utf-8");
    const deps = [...src.matchAll(/from\s+"(@\/[^"]+)"/g)].map((m) => resolveImport(m[1])).filter((f): f is string => !!f);
    return { route: routeFor(file), text: [src, ...deps.map((d) => readFileSync(d, "utf-8"))].join("\n") };
  });
  return corpus;
}

const stem = (artifact: string) => artifact.replace(/\\/g, "/").split("/").pop()!.replace(/\.(json|md|jsonl)$/, "");

export function quotedOn(artifact: string, papersDir = join(ROOT, "..", "docs", "papers")): QuotedOn[] {
  const key = stem(artifact);
  if (!key) return [];
  const routes = routeTexts().filter((r) => r.text.includes(key)).map((r) => ({ label: r.route, href: r.route }));
  const papers = existsSync(papersDir)
    ? readdirSync(papersDir).filter((f) => f.endsWith(".md") && readFileSync(join(papersDir, f), "utf-8").includes(key))
      .map((f) => ({ label: `docs/papers/${f}`, href: `https://github.com/neeljshah/court-vision/blob/master/docs/papers/${f}` }))
    : [];
  return [...routes.sort((a, b) => a.href.localeCompare(b.href)), ...papers];
}
