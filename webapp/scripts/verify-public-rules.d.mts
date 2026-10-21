// Type surface of verify-public-rules.mjs for the vitest files that import it (tsc runs on tests too).
export const CANONICAL_HEADLINE_KEYS: string[];
export const CHECK_STATUSES: string[];
export const UPTIME_NUMERICS: string[];
export const UPTIME_RE: RegExp;
export type ArtifactRule = {
  file: string | ((root: string) => string | null);
  root?: "repo";
  demo?: boolean;
  label?: string;
  check: (value: unknown, where: string) => string[];
};
export const ARTIFACT_RULES: ArtifactRule[];
export function newestUptime(repoRoot: string): string | null;
export function runArtifactRules(options: { webappRoot: string; repoRoot: string; snapshot?: boolean }): {
  checked: number;
  failures: string[];
};
