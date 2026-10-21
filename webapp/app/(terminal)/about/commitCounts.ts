// commitCounts.ts -- the about page's commit figures, counted from the public repository's
// git history on master, pinned to the sha below, with the two commands below (never quoted
// from a document). To refresh: run both on a full (not shallow) clone and update sha, asOf, total and
// agentCoAuthored together. The page prints the method and the date beside the numbers,
// the share is computed from the counts (never typed), and about/page.test.tsx checks it.
import { REPO_URL } from "@/components/evidence/kit";

export const COMMIT_COUNTS = {
  /** The day the commands were run (the counts move with every push to master). */
  asOf: "2026-10-21",
  branch: "master",
  /** The commit the counts were taken at; the receipt commands and link pin to it (master moves). */
  sha: "4f033b5a5",
  /** git rev-list --count <sha> */
  total: 6556,
  /** Commits whose message carries a Co-Authored-By line naming Claude or Codex. */
  agentCoAuthored: 1620,
} as const;

export const COMMIT_COUNT_COMMANDS = {
  total: `git rev-list --count ${COMMIT_COUNTS.sha}`,
  agentCoAuthored:
    `git log ${COMMIT_COUNTS.sha} -i --grep='^Co-Authored-By:.*\\(Claude\\|Codex\\)' --format=%H | wc -l`,
} as const;

/** The receipt: both commands, as one copyable line. */
export const COMMIT_COUNT_RECEIPT = `${COMMIT_COUNT_COMMANDS.total}; ${COMMIT_COUNT_COMMANDS.agentCoAuthored}`;

/** The counted history on GitHub (what the commands walk). */
export const COMMIT_HISTORY_URL = `${REPO_URL}/commits/${COMMIT_COUNTS.sha}`;

/** The share as a one-decimal percentage, computed from the two counts. */
export function agentShare(c: { total: number; agentCoAuthored: number } = COMMIT_COUNTS): string {
  return `${((100 * c.agentCoAuthored) / c.total).toFixed(1)}%`;
}

export const fmtCommits = (n: number): string => n.toLocaleString("en-US");
