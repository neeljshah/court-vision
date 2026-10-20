// Type surface of gen-figures.mjs for the vitest files that import it (tsc runs on tests too).
export const WEBAPP_ROOT: string;
export const REPO_ROOT: string;
export const FIGURES_JSON: string;
export const DEFAULT_IN: string;
export const DEFAULT_OUT: string;
export const SCHEMA: string;
export class FiguresError extends Error {}
export function normalize(cfg: unknown, label?: string): {
  asOf: string;
  retracted: string[];
  countFigures: Record<string, Record<string, unknown>>;
  comparisonFigures: Record<string, Record<string, unknown>>;
};
export function generate(cfg: unknown, label?: string): string;
export function generateFromFile(inPath?: string): string;
export function main(argv?: string[]): number;
