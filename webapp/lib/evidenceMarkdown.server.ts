// evidenceMarkdown.server.ts -- the plain heading/table/image splitter for one
// docs/evidence/<slug>.md claim page (no gray-matter dep). Build-time only; used by
// lib/evidence.server buildClaimPage. A gap in the markdown (a missing heading, a
// Receipts section with no table, an image that is not staged, a Reproduce section
// with no code block) is logged by slug through report() and the section renders
// empty: the build log names the page, and no prose is ever invented.

import { existsSync } from "node:fs";
import { join } from "node:path";

const SHOWCASE_IMG_DIR = join(process.cwd(), "public", "img", "showcase");

export type ReceiptRow = { guarantee: string; artifact: string; receipt: string };
export type ClaimFigure = { src: string; alt: string; caption: string };

// A gap in a claim's markdown is logged once per (slug, gap) and the section renders
// empty as before: the build log names the page, and no prose is ever invented.
const reported = new Set<string>();
export function report(slug: string, what: string): void {
  const key = `${slug}:${what}`;
  if (reported.has(key)) return;
  reported.add(key);
  console.warn(`evidence: docs/evidence/${slug}.md ${what}`);
}

// Split the body into { lowercased "## heading" -> content } sections.
export function splitHeadings(body: string): Map<string, string> {
  const map = new Map<string, string>();
  const parts = body.split(/^## +/m); // parts[0] = title + lede preamble
  for (let i = 1; i < parts.length; i++) {
    const nl = parts[i].indexOf("\n");
    const head = (nl < 0 ? parts[i] : parts[i].slice(0, nl)).trim();
    const content = nl < 0 ? "" : parts[i].slice(nl + 1).trim();
    map.set(head.toLowerCase(), content);
  }
  return map;
}

// Title (# ...) + lede (the leading > blockquote) from the preamble.
export function parseHead(md: string, slug: string): { title: string; lede: string } {
  let title = "";
  const lede: string[] = [];
  for (const line of md.split("\n")) {
    if (!title) {
      if (line.startsWith("# ")) title = line.slice(2).trim();
      continue;
    }
    const t = line.trim();
    if (t.startsWith(">")) lede.push(line.replace(/^\s*>\s?/, "").trim());
    else if (t === "---") break;
    else if (t === "") continue;
    else if (lede.length) break; // first prose line after the quote ends it
  }
  if (!title) report(slug, 'has no "# title" line');
  return { title, lede: lede.join(" ").trim() };
}

// Markdown pipe table -> rows. The evidence md tables are NOT uniform: they run
// 2-4 columns and put the artifact/path column in position 1, 2, or last
// depending on the page. So the artifact column is detected by CONTENT (the
// column whose body cells most often carry a file-path token), never a fixed
// index -- the old `cells.length >= 3` + `r[1]` assumption silently dropped
// every 2-column table (e.g. ingame-conditioning's `| Number | Artifact path |`)
// and mislabeled every table whose path sat in the last column.
const PATH_RE =
  /`[^`]*[./][^`]*`|\b\w[\w./-]*\.(json|py|md|ts|tsx|sql|jsonl)\b|scripts\/|src\/|docs\//;

export function parseTable(section: string, slug: string): ReceiptRow[] {
  if (!section) return []; // the missing heading was already reported by pickSection
  const rows: string[][] = [];
  for (const line of section.split("\n")) {
    const t = line.trim();
    if (!t.startsWith("|")) continue;
    const cells = t.split("|").slice(1, -1).map((c) => c.trim());
    if (cells.length >= 2) rows.push(cells);
  }
  const noSep = rows.filter((r) => !r.every((c) => /^:?-{2,}:?$/.test(c)));
  if (noSep.length < 2) {
    report(slug, "has a Receipts section with no table rows");
    return []; // header + separator only, no body
  }
  const header = noSep[0].map((c) => c.toLowerCase());
  const body = noSep.slice(1);
  const ncols = header.length;
  let artCol = ncols - 1;
  let best = -1;
  for (let c = 0; c < ncols; c++) {
    const hits = body.filter((r) => PATH_RE.test(r[c] ?? "")).length;
    if (hits > best) {
      best = hits;
      artCol = c;
    }
  }
  // Optional receipt/value column: a header-named one that is neither the
  // guarantee (col 0) nor the detected artifact column.
  const recCol = header.findIndex(
    (h, c) =>
      c !== 0 &&
      c !== artCol &&
      /receipt|result|status|honest|label|scale|verdict/.test(h),
  );
  return body.map((r) => ({
    guarantee: r[0] ?? "",
    artifact: r[artCol] ?? "",
    receipt: recCol >= 0 ? r[recCol] ?? "" : "",
  }));
}

// ![alt](src) images -> staged public paths, paired in order with the italic
// *Figure: ...* captions that follow them.
export function parseFigures(body: string, slug: string): ClaimFigure[] {
  const figs: ClaimFigure[] = [];
  const imgRe = /!\[([^\]]*)\]\(([^)]+)\)/g;
  let m: RegExpExecArray | null;
  while ((m = imgRe.exec(body))) {
    const base = m[2].split("/").pop() || m[2];
    figs.push({ src: `img/showcase/${base}`, alt: m[1].trim(), caption: "" });
  }
  const caps: string[] = [];
  const capRe = /\*Figure:([\s\S]*?)\*/g;
  let cm: RegExpExecArray | null;
  while ((cm = capRe.exec(body))) {
    caps.push(("Figure:" + cm[1]).replace(/\s+/g, " ").trim());
  }
  figs.forEach((f, i) => {
    if (caps[i]) f.caption = caps[i];
  });
  // Only figures actually staged under public/img/showcase ship; an unstaged
  // image would render as a broken <img> on the public site, so it is dropped and logged.
  return figs.filter((f) => {
    const base = f.src.split("/").pop() || "";
    if (existsSync(join(SHOWCASE_IMG_DIR, base))) return true;
    report(slug, `cites image ${base}, which is not staged under public/img/showcase`);
    return false;
  });
}

export function parseReproduce(section: string, slug: string): string {
  const m = section.match(/```[a-z]*\n([\s\S]*?)```/);
  if (section && !m) report(slug, "has a Reproduce section with no code block");
  return m ? m[1].replace(/\s+$/, "") : "";
}

// Section headings in the evidence md are NOT fixed strings: "Receipts" also
// appears as "Receipts -- verified committed paths", "Reproduce" as "Reproduce
// on a fresh clone" / "Reproduce (per-file only)" / "How to reproduce", "Why
// this matters" as "Why it matters to an employer", etc. Match by regex over the
// lowercased heading so a suffix never drops a whole section (the exact-string
// lookup was the join gap that blanked receipts + reproduce on many claims).
export function pickSection(sec: Map<string, string>, re: RegExp, slug: string, name: string): string {
  for (const [k, v] of sec) if (re.test(k)) return v;
  report(slug, `has no "## ${name}" heading`);
  return "";
}
