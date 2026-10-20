// workingPapers.server.ts -- build-time reader for the three readouts under docs/papers/*.md.
// Title = first "# " line; byline = the next paragraph; abstract = the first three sentences
// of the "**Summary.**" paragraph (T3 caps abstracts at five). Server-only (node:fs).
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

export type WorkingPaper = { file: string; title: string; byline: string; abstract: string; date: string | null };

export const PAPERS_DIR = "docs/papers";

export function parseWorkingPaper(file: string, md: string): WorkingPaper | null {
  const paras = md.replace(/\r/g, "").split(/\n\s*\n/).map((p) => p.replace(/\s*\n\s*/g, " ").trim());
  const title = paras.find((p) => p.startsWith("# "))?.slice(2).trim();
  if (!title) return null;
  const byline = paras[paras.findIndex((p) => p.startsWith("# ")) + 1] ?? "";
  const summary = (paras.find((p) => p.startsWith("**Summary.**")) ?? "").replace("**Summary.**", "").trim();
  const sentences = summary.split(/(?<=[.?!])\s+(?=[A-Z])/).slice(0, 3);
  const date = byline.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? null;
  return { file: `${PAPERS_DIR}/${file}`, title, byline, abstract: sentences.join(" "), date };
}

export function loadWorkingPapers(dir = join(process.cwd(), "..", PAPERS_DIR)): WorkingPaper[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith(".md"))
    .sort()
    .map((f) => parseWorkingPaper(f, readFileSync(join(dir, f), "utf-8")))
    .filter((p): p is WorkingPaper => p !== null);
}
