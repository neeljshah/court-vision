// kit.ts -- shared helpers for the evidence kit: the GitHub blob link under master,
// the packet link, repo-path normalization, as-of day extraction and the ONE set of
// number formats every canonical figure is rendered with. No React, no node:fs, so
// every component here is safe in both server and client trees.
import { artifactUrl } from "@/lib/analytics/artifactProvenance";

export const REPO_URL = "https://github.com/neeljshah/court-vision";
export const REPO_BRANCH = "master";
export const PACKET_PATH = "docs/JOB_EVIDENCE_PACKET.md";

/** The packet's verification vocabulary for a receipt (edge_claimed:false is the calibration-only stamp). */
export type ReceiptStatus = "edge_claimed:false" | "descriptive_only" | "validation_pending";
export const RECEIPT_STATUSES: readonly ReceiptStatus[] = ["edge_claimed:false", "descriptive_only", "validation_pending"];

// Roots that exist in the public repository (scripts/hooks/public_allowlist.txt); a path
// outside them is not linked, because a GitHub blob link to it would 404.
const PUBLIC_ROOTS = ["docs/", "webapp/", "scripts/", "kernel/", "domains/", "tests/", "results/", ".github/"];
const ROOT_FILES = new Set([
  "README.md", "EVIDENCE.md", "RECEIPTS.md", "REPRODUCE.md", "ARCHITECTURE.md", "VISION.md",
  "CHANGELOG.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "SECURITY.md", "CITATION.cff", "LICENSE",
]);
const PATH_SHAPE = /^(?:[A-Za-z0-9_.()[\]-]+\/)*[A-Za-z0-9_.()[\]-]+\/?$/;

/** Backslashes to slashes, no leading ./, and the analytics pages' webapp-relative public/ paths made repo-relative. */
export function normalizeRepoPath(source: string): string {
  const path = source.trim().replace(/\\/g, "/").replace(/^\.\//, "").replace(/^\/+/, "");
  return path.startsWith("public/data/") ? `webapp/${path}` : path;
}

/** True when the source is a repo-relative path under a root the public repository holds. */
export function isRepoPath(source: string): boolean {
  const path = normalizeRepoPath(source);
  if (!path || !PATH_SHAPE.test(path) || path.split("/").includes("..")) return false;
  return ROOT_FILES.has(path) || PUBLIC_ROOTS.some((root) => path.startsWith(root));
}

/** GitHub blob URL of a repo path on master (parentheses kept readable, everything else encoded). */
export function blobUrl(path: string): string {
  const encoded = normalizeRepoPath(path).split("/").map((segment) => encodeURIComponent(segment)
    .replace(/%28/g, "(").replace(/%29/g, ")")).join("/");
  return `${REPO_URL}/blob/${REPO_BRANCH}/${encoded}`;
}

export const PACKET_HREF = blobUrl(PACKET_PATH);

/**
 * Where a receipt links: an explicit href wins; a repo path links to its GitHub blob on
 * master; a bare published artifact name links to the exported JSON on this site; anything
 * else (a command, a sentence) has no link and the chip says so.
 */
export function receiptHref(source: string, explicit?: string | null): string | null {
  if (explicit) return explicit;
  if (isRepoPath(source)) return blobUrl(source);
  return artifactUrl(source);
}

export function basename(path: string): string {
  const parts = normalizeRepoPath(path).replace(/\/$/, "").split("/");
  return parts[parts.length - 1] || path;
}

/** The calendar day of an ISO date or timestamp; null for anything else (placeholders stay unpublished). */
export function dayOf(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$/.exec(value.trim());
  if (!match) return null;
  const [year, month, day] = match.slice(1).map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const valid = date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  return valid ? value.trim().slice(0, 10) : null;
}

export const fmtSigned = (value: number, digits = 4): string => `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
export const fmtDecimal = (value: number, digits = 4): string => value.toFixed(digits);
export const fmtCount = (value: number): string => value.toLocaleString("en-US");
export const fmtInterval = (ci: readonly [number, number] | readonly number[]): string =>
  `[${fmtSigned(ci[0])}, ${fmtSigned(ci[1])}]`;

const SIGNED_FIELDS = new Set(["gap"]);
const DECIMAL_FIELDS = new Set(["model", "close", "mde"]);

/** The one formatter for a canonical figure field: gaps signed, scores to 4 places, counts with separators. */
export function formatFigureField(field: string, value: unknown): string {
  if (value == null) return "not published";
  if (Array.isArray(value) && value.length === 2 && value.every((v) => typeof v === "number")) {
    return fmtInterval(value as number[]);
  }
  if (typeof value === "number") {
    if (SIGNED_FIELDS.has(field)) return fmtSigned(value);
    if (DECIMAL_FIELDS.has(field)) return fmtDecimal(value);
    return Number.isInteger(value) ? fmtCount(value) : fmtDecimal(value);
  }
  return String(value);
}
