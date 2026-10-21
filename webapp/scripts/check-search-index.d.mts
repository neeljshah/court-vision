// Type surface of check-search-index.mjs for the vitest files that import it (tsc runs on tests too).
export const REQUIRED_PAGES: string[];
export function exportedFile(outDir: string, href: string): string | null;
export function isRedirectStub(html: string): boolean;
export function checkIndex(outDir: string, records: Array<{ id: string; href: string }>): string[];
