// evidenceLinks.ts -- resolve the relative links inside docs/evidence/<slug>.md
// for the exported site. The markdown is written for GitHub, where
// "../JOB_EVIDENCE_PACKET.md" resolves against docs/evidence/; rendered as-is on
// the static site the same href 404s. A sibling claim file becomes its own
// /evidence page (basePath-prefixed, because the prose renders a plain <a>, not
// <Link>); every other repo-relative target becomes the GitHub blob/tree URL.
// Absolute URLs, anchors and mailto: pass through untouched. Pure (no fs) so it
// is unit-testable; evidence.server.ts applies it at build time.

const REPO = "https://github.com/neeljshah/court-vision";
const BRANCH = "master";
const MD_DIR = "docs/evidence";

function repoPathFor(relativeHref: string): string {
  const out: string[] = [];
  for (const seg of `${MD_DIR}/${relativeHref}`.split("/")) {
    if (seg === "..") out.pop();
    else if (seg && seg !== ".") out.push(seg);
  }
  return out.join("/");
}

/** Resolve one markdown link target found in an evidence claim file. */
export function resolveEvidenceHref(
  href: string,
  claimSlugs: ReadonlySet<string>,
  basePath = "",
): string {
  const raw = href.trim();
  if (!raw || /^(?:[a-z][a-z0-9+.-]*:|#|\/)/i.test(raw)) return href;
  const hashAt = raw.indexOf("#");
  const path = hashAt >= 0 ? raw.slice(0, hashAt) : raw;
  const hash = hashAt >= 0 ? raw.slice(hashAt) : "";
  const sibling = /^([a-z0-9][a-z0-9-]*)\.md$/i.exec(path);
  if (sibling && claimSlugs.has(sibling[1])) return `${basePath}/evidence/${sibling[1]}/${hash}`;
  const repoPath = repoPathFor(path);
  if (path.endsWith("/")) return `${REPO}/tree/${BRANCH}/${repoPath}/`;
  return `${REPO}/blob/${BRANCH}/${repoPath}${hash}`;
}

// [text](target) -- the lookbehind keeps ![alt](src) images out of the match without
// swallowing the character before an adjacent link. ponytail: a linked image [![alt](src)](href)
// is still rewritten at its inner image; a real markdown parser is the upgrade path.
const MD_LINK = /(?<!!)\[([^\]\n]+?)\]\(([^)\s]+?)\)/g;

/** Rewrite every markdown link target in a claim's body (images untouched). */
export function rewriteEvidenceLinks(
  markdown: string,
  claimSlugs: ReadonlySet<string>,
  basePath = "",
): string {
  return markdown.replace(
    MD_LINK,
    (_m, text: string, target: string) =>
      `[${text}](${resolveEvidenceHref(target, claimSlugs, basePath)})`,
  );
}
