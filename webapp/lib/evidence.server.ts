// evidence.server.ts -- build-time reader for the evidence spine.
//
// Two sources, joined at build:
//   1. public/data/showcase/evidence_index.json (staged, /receipts pattern) --
//      bucket order, per-claim title/teaser, strongest receipt, cited artifacts,
//      edge_claimed:false. This is the truth-source for the index + receipt join.
//   2. ../docs/evidence/<slug>.md -- the full claim prose. These .md are tracked
//      in the public repo (NOT gitignored), so they ship with a fresh clone; we
//      parse them with a plain heading/table splitter (no gray-matter dep).
//
// Honesty: if a claim's .md is absent (a corrupt/partial clone), the page still
// renders from the staged index with status VALIDATION_PENDING -- never a blank,
// never invented prose. All image srcs resolve to the staged public tree
// (img/showcase/<basename>); no C:/Users path can appear.

import { readFileSync } from "node:fs";
import { join } from "node:path";

const SHOWCASE_DIR = join(process.cwd(), "public", "data", "showcase");
// docs/evidence sits at the repo root, one level up from the webapp cwd.
const EVIDENCE_DIR = join(process.cwd(), "..", "docs", "evidence");

// The retraction story renders on its own /evidence/retraction-story route
// (retraction framing is load-bearing), so it is excluded from the [claim]
// dynamic params -- but it still appears as a row in the index.
export const RETRACTION_SLUG = "retraction-story";

export type StrongestReceipt = { source: string | null; label: string };

export type ClaimIndexEntry = {
  slug: string;
  bucket: string;
  title: string;
  claim: string; // teaser from the index (not the full md body)
  receipt: StrongestReceipt;
  citedArtifacts: string[];
  edgeClaimed: boolean;
};

export type ClaimBucket = { name: string; claims: ClaimIndexEntry[] };
export type ClaimIndex = {
  buckets: ClaimBucket[];
  claimCount: number;
  edgeClaimed: boolean;
};

export type ReceiptRow = { guarantee: string; artifact: string; receipt: string };
export type ClaimFigure = { src: string; alt: string; caption: string };

export type ClaimPageProps = {
  slug: string;
  title: string;
  lede: string;
  bucket: string;
  claim: string; // full "## The claim" body (markdown)
  howItWorks: string;
  whyMatters: string;
  receipts: ReceiptRow[];
  figures: ClaimFigure[];
  reproduce: string;
  strongestReceipt: StrongestReceipt;
  citedArtifacts: string[];
  edgeClaimed: boolean;
  status: "MEASURED" | "VALIDATION_PENDING";
};

type RawReceipt = { source?: string | null; label?: string | null };
type RawClaim = {
  slug: string;
  bucket: string;
  title: string;
  claim?: string;
  strongest_receipt?: RawReceipt | null;
  cited_artifacts?: string[];
  edge_claimed?: boolean;
};
type RawIndex = {
  claim_count?: number;
  bucket_order?: string[];
  edge_claimed?: boolean;
  claims?: RawClaim[];
};

function loadIndex(): RawIndex | null {
  try {
    return JSON.parse(
      readFileSync(join(SHOWCASE_DIR, "evidence_index.json"), "utf-8"),
    ) as RawIndex;
  } catch {
    return null;
  }
}

function toReceipt(r: RawReceipt | null | undefined): StrongestReceipt {
  return { source: r?.source ?? null, label: r?.label ?? "" };
}

function toEntry(c: RawClaim): ClaimIndexEntry {
  return {
    slug: c.slug,
    bucket: c.bucket,
    title: c.title,
    claim: c.claim ?? "",
    receipt: toReceipt(c.strongest_receipt),
    citedArtifacts: c.cited_artifacts ?? [],
    edgeClaimed: c.edge_claimed === true,
  };
}

// The 4-bucket index, ordered by the index's own bucket_order. Includes all 23
// claims (retraction-story too -- its row links to its dedicated page).
export function buildClaimIndex(): ClaimIndex {
  const idx = loadIndex();
  const claims = idx?.claims ?? [];
  const byBucket = new Map<string, ClaimIndexEntry[]>();
  for (const c of claims) {
    const e = toEntry(c);
    const list = byBucket.get(e.bucket);
    if (list) list.push(e);
    else byBucket.set(e.bucket, [e]);
  }
  const order = idx?.bucket_order ?? [];
  const buckets: ClaimBucket[] = [];
  for (const name of order) {
    const list = byBucket.get(name);
    if (list) buckets.push({ name, claims: list });
  }
  // Any bucket the order didn't mention (defensive) trails after, so no claim
  // is ever silently dropped from the index.
  for (const [name, list] of byBucket) {
    if (!order.includes(name)) buckets.push({ name, claims: list });
  }
  return {
    buckets,
    claimCount: claims.length,
    edgeClaimed: idx?.edge_claimed === true,
  };
}

// The 22 slugs for generateStaticParams on the [claim] dynamic route
// (retraction-story is excluded -- it owns a static route).
export function listClaimSlugs(): string[] {
  const idx = loadIndex();
  return (idx?.claims ?? [])
    .map((c) => c.slug)
    .filter((s) => s !== RETRACTION_SLUG);
}

// ponytail: slug is a route param -- allow only kebab basenames so a crafted
// `../../secrets` can never escape docs/evidence. Trust boundary.
function safeSlug(slug: string): string | null {
  return /^[a-z0-9-]+$/.test(slug) && !slug.includes("..") ? slug : null;
}

// Split the body into { lowercased "## heading" -> content } sections.
function splitHeadings(body: string): Map<string, string> {
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
function parseHead(md: string): { title: string; lede: string } {
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

function parseTable(section: string): ReceiptRow[] {
  const rows: string[][] = [];
  for (const line of section.split("\n")) {
    const t = line.trim();
    if (!t.startsWith("|")) continue;
    const cells = t.split("|").slice(1, -1).map((c) => c.trim());
    if (cells.length >= 2) rows.push(cells);
  }
  const noSep = rows.filter((r) => !r.every((c) => /^:?-{2,}:?$/.test(c)));
  if (noSep.length < 2) return []; // header + separator only, no body
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
function parseFigures(body: string): ClaimFigure[] {
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
  return figs;
}

function parseReproduce(section: string): string {
  const m = section.match(/```[a-z]*\n([\s\S]*?)```/);
  return m ? m[1].replace(/\s+$/, "") : "";
}

// Section headings in the evidence md are NOT fixed strings: "Receipts" also
// appears as "Receipts -- verified committed paths", "Reproduce" as "Reproduce
// on a fresh clone" / "Reproduce (per-file only)" / "How to reproduce", "Why
// this matters" as "Why it matters to an employer", etc. Match by regex over the
// lowercased heading so a suffix never drops a whole section (the exact-string
// lookup was the join gap that blanked receipts + reproduce on many claims).
function pickSection(sec: Map<string, string>, re: RegExp): string {
  for (const [k, v] of sec) if (re.test(k)) return v;
  return "";
}

// Fresh-clone / missing-md fallback: render from the staged index only.
function pendingPage(c: RawClaim): ClaimPageProps {
  return {
    slug: c.slug,
    title: c.title,
    lede: "",
    bucket: c.bucket,
    claim: c.claim ?? "",
    howItWorks: "",
    whyMatters: "",
    receipts: [],
    figures: [],
    reproduce: "",
    strongestReceipt: toReceipt(c.strongest_receipt),
    citedArtifacts: c.cited_artifacts ?? [],
    edgeClaimed: c.edge_claimed === true,
    status: "VALIDATION_PENDING",
  };
}

// Full page props for one claim: parse its .md, join the index receipt/bucket.
export function buildClaimPage(slug: string): ClaimPageProps | null {
  const clean = safeSlug(slug);
  if (!clean) return null;
  const raw = loadIndex()?.claims?.find((c) => c.slug === clean) ?? null;

  let md = "";
  try {
    md = readFileSync(join(EVIDENCE_DIR, `${clean}.md`), "utf-8");
  } catch {
    md = "";
  }
  if (!md) return raw ? pendingPage(raw) : null;

  const cut = md.indexOf("<!-- nav-footer -->");
  const body = cut >= 0 ? md.slice(0, cut) : md;
  const head = parseHead(body);
  const sec = splitHeadings(body);

  return {
    slug: clean,
    title: head.title || raw?.title || clean,
    lede: head.lede,
    bucket: raw?.bucket ?? "",
    claim: pickSection(sec, /^the claim/),
    howItWorks: pickSection(sec, /^how it works/),
    whyMatters: pickSection(sec, /^why (this|it) matters/),
    receipts: parseTable(pickSection(sec, /^receipts\b/)),
    figures: parseFigures(body),
    reproduce: parseReproduce(pickSection(sec, /reproduce/)),
    strongestReceipt: toReceipt(raw?.strongest_receipt),
    citedArtifacts: raw?.cited_artifacts ?? [],
    edgeClaimed: raw?.edge_claimed === true,
    status: "MEASURED",
  };
}
