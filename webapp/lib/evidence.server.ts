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
// Honesty: the index is the spine, so a missing or corrupt index, an empty claim
// list, or a claim set that disagrees with the docs/evidence/<slug>.md files THROWS
// at build time (readEvidenceIndex) -- a null would drop every /evidence/<slug> page
// with a green build. A claim whose .md is empty still renders from the index with
// status VALIDATION_PENDING -- never a blank, never invented prose. A gap inside a
// claim's markdown (a heading, the receipts table, an unstaged image) is logged by
// slug, never silently blanked. All image srcs resolve to the staged public tree
// (img/showcase/<basename>); no C:/Users path can appear.

import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { rewriteEvidenceLinks } from "@/lib/evidenceLinks";
import {
  parseFigures, parseHead, parseReproduce, parseTable, pickSection, splitHeadings,
  type ClaimFigure, type ReceiptRow,
} from "@/lib/evidenceMarkdown.server";

export type { ClaimFigure, ReceiptRow };

// Claim prose renders plain <a>, so site-internal links need the export basePath.
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

const SHOWCASE_DIR = join(process.cwd(), "public", "data", "showcase");
// docs/evidence sits at the repo root, one level up from the webapp cwd.
const EVIDENCE_DIR = join(process.cwd(), "..", "docs", "evidence");

// The retraction story renders on its own /evidence/retraction-story route
// (retraction framing is load-bearing), so it is excluded from the [claim]
// dynamic params -- but it still appears as a row in the index.
export const RETRACTION_SLUG = "retraction-story";

export type StrongestReceipt = { source: string | null; label: string };

/**
 * The receipt-chip verification of a claim. edge_claimed:false ONLY when the index
 * says `edge_claimed: false` explicitly; an absent key is pending, never verified
 * (the same rule as showcase.server receiptChip).
 */
export type EdgeVerified = "edge_claimed:false" | "validation_pending";

export type ClaimIndexEntry = {
  slug: string;
  bucket: string;
  title: string;
  claim: string; // teaser from the index (not the full md body)
  receipt: StrongestReceipt;
  citedArtifacts: string[];
  edgeClaimed: boolean;
  verified: EdgeVerified;
};

export type ClaimBucket = { name: string; claims: ClaimIndexEntry[] };
export type ClaimIndex = {
  buckets: ClaimBucket[];
  claimCount: number;
  edgeClaimed: boolean;
};

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
  verified: EdgeVerified;
  status: "MEASURED" | "VALIDATION_PENDING";
};

export type RawReceipt = { source?: string | null; label?: string | null };
export type RawClaim = {
  slug: string;
  bucket: string;
  title: string;
  claim?: string;
  strongest_receipt?: RawReceipt | null;
  cited_artifacts?: string[];
  edge_claimed?: boolean;
};
export type RawIndex = {
  claim_count?: number;
  bucket_order?: string[];
  edge_claimed?: boolean;
  claims?: RawClaim[];
};

const INDEX_FILE = join(SHOWCASE_DIR, "evidence_index.json");
const SLUG_MD = /^[a-z0-9-]+\.md$/;
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));

/**
 * Read and check the staged index. Throws (a build-time failure) when the file is
 * missing or corrupt, when it has no claims, or when claim_count, claims.length and
 * the set of docs/evidence/<slug>.md files disagree: every /evidence/<slug> page is
 * generated from this file, so a silent null would drop them all with a green build.
 */
export function readEvidenceIndex(file = INDEX_FILE, evidenceDir = EVIDENCE_DIR): RawIndex {
  const label = relative(process.cwd(), file) || file;
  let raw: string;
  try {
    raw = readFileSync(file, "utf-8");
  } catch (e) {
    throw new Error(`evidence: ${label} is missing or unreadable (${msg(e)}); every /evidence page is built from it`);
  }
  let idx: RawIndex;
  try {
    idx = JSON.parse(raw) as RawIndex;
  } catch (e) {
    throw new Error(`evidence: ${label} is not valid JSON: ${msg(e)}`);
  }
  const claims = idx?.claims;
  if (!Array.isArray(claims) || claims.length === 0) throw new Error(`evidence: ${label} has no claims`);
  const slugs = claims.map((c) => c.slug);
  let docs: string[];
  try {
    docs = readdirSync(evidenceDir).filter((n) => SLUG_MD.test(n)).map((n) => n.slice(0, -3));
  } catch (e) {
    throw new Error(`evidence: cannot list ${evidenceDir}: ${msg(e)}`);
  }
  const missing = slugs.filter((s) => !docs.includes(s));
  const extra = docs.filter((d) => !slugs.includes(d));
  if (idx.claim_count !== claims.length || missing.length || extra.length) {
    throw new Error(
      `evidence: ${label} claim_count=${idx.claim_count}, claims=${claims.length}, docs/evidence/<slug>.md files=${docs.length}` +
        (missing.length ? `; no .md for ${missing.join(", ")}` : "") +
        (extra.length ? `; .md without an index row: ${extra.join(", ")}` : ""),
    );
  }
  return idx;
}

let indexCache: RawIndex | null = null;
function loadIndex(): RawIndex {
  if (!indexCache) indexCache = readEvidenceIndex();
  return indexCache;
}

function toReceipt(r: RawReceipt | null | undefined): StrongestReceipt {
  return { source: r?.source ?? null, label: r?.label ?? "" };
}

const verifiedOf = (c: RawClaim): EdgeVerified =>
  c.edge_claimed === false ? "edge_claimed:false" : "validation_pending";

function toEntry(c: RawClaim): ClaimIndexEntry {
  return {
    slug: c.slug,
    bucket: c.bucket,
    title: c.title,
    claim: c.claim ?? "",
    receipt: toReceipt(c.strongest_receipt),
    citedArtifacts: c.cited_artifacts ?? [],
    edgeClaimed: c.edge_claimed === true,
    verified: verifiedOf(c),
  };
}

// The 4-bucket index, ordered by the index's own bucket_order. Includes all 23
// claims (retraction-story too -- its row links to its dedicated page).
export function buildClaimIndex(idx: RawIndex = loadIndex()): ClaimIndex {
  const claims = idx.claims ?? [];
  const byBucket = new Map<string, ClaimIndexEntry[]>();
  for (const c of claims) {
    const e = toEntry(c);
    const list = byBucket.get(e.bucket);
    if (list) list.push(e);
    else byBucket.set(e.bucket, [e]);
  }
  const order = idx.bucket_order ?? [];
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
    edgeClaimed: idx.edge_claimed === true,
  };
}

// The 22 slugs for generateStaticParams on the [claim] dynamic route
// (retraction-story is excluded -- it owns a static route).
export function listClaimSlugs(idx: RawIndex = loadIndex()): string[] {
  return (idx.claims ?? [])
    .map((c) => c.slug)
    .filter((s) => s !== RETRACTION_SLUG);
}

// ponytail: slug is a route param -- allow only kebab basenames so a crafted
// `../../secrets` can never escape docs/evidence. Trust boundary.
function safeSlug(slug: string): string | null {
  return /^[a-z0-9-]+$/.test(slug) && !slug.includes("..") ? slug : null;
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
    verified: verifiedOf(c),
    status: "VALIDATION_PENDING",
  };
}

// Full page props for one claim: parse its .md, join the index receipt/bucket.
// `src` overrides the staged index / docs/evidence directory (tests).
export function buildClaimPage(
  slug: string,
  src: { index?: RawIndex; evidenceDir?: string } = {},
): ClaimPageProps | null {
  const clean = safeSlug(slug);
  if (!clean) return null;
  const idx = src.index ?? loadIndex();
  const raw = idx.claims?.find((c) => c.slug === clean) ?? null;

  let md = "";
  try {
    md = readFileSync(join(src.evidenceDir ?? EVIDENCE_DIR, `${clean}.md`), "utf-8");
  } catch {
    md = "";
  }
  if (!md) return raw ? pendingPage(raw) : null;
  // The md is written for GitHub; rewrite its relative links for the static site.
  md = rewriteEvidenceLinks(md, new Set([...listClaimSlugs(idx), RETRACTION_SLUG]), BASE_PATH);

  const cut = md.indexOf("<!-- nav-footer -->");
  const body = cut >= 0 ? md.slice(0, cut) : md;
  const head = parseHead(body, clean);
  const sec = splitHeadings(body);

  return {
    slug: clean,
    title: head.title || raw?.title || clean,
    lede: head.lede,
    bucket: raw?.bucket ?? "",
    claim: pickSection(sec, /^the claim/, clean, "The claim"),
    howItWorks: pickSection(sec, /^how it works/, clean, "How it works"),
    whyMatters: pickSection(sec, /^why (this|it) matters/, clean, "Why this matters"),
    receipts: parseTable(pickSection(sec, /^receipts\b/, clean, "Receipts"), clean),
    figures: parseFigures(body, clean),
    reproduce: parseReproduce(pickSection(sec, /reproduce/, clean, "Reproduce"), clean),
    strongestReceipt: toReceipt(raw?.strongest_receipt),
    citedArtifacts: raw?.cited_artifacts ?? [],
    edgeClaimed: raw?.edge_claimed === true,
    verified: raw ? verifiedOf(raw) : "validation_pending",
    status: "MEASURED",
  };
}
