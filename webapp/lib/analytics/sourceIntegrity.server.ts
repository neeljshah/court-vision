import { readFileSync } from "node:fs";
import { join } from "node:path";
import { sourceModuleIds } from "./scoutIntegrity";

type AskSource = {
  entries?: Array<{ a?: { source_artifact?: unknown; source_module_ids?: unknown } }>;
};

const ASK_CITATION = /^webapp\/public\/data\/ask\/([a-z0-9_-]+)\.json$/i;

function askModuleIds(file: string): string[] {
  const value: unknown = JSON.parse(readFileSync(join(process.cwd(), "public", "data", "ask", `${file}.json`), "utf8"));
  if (!value || typeof value !== "object") return [];
  const entries = (value as AskSource).entries;
  if (!Array.isArray(entries)) return [];
  const artifacts = entries.flatMap(entry => typeof entry.a?.source_artifact === "string" ? [entry.a.source_artifact] : []);
  const declared = entries.flatMap(entry => Array.isArray(entry.a?.source_module_ids) ? entry.a.source_module_ids.filter((id): id is string => typeof id === "string") : []);
  return [...sourceModuleIds(artifacts), ...declared];
}

/** Resolves exact public JSON citations, including structured Ask citation files. */
export function moduleIdsForCitations(citations: readonly string[]): string[] {
  const direct = sourceModuleIds(citations);
  const indirect = citations.flatMap(citation => {
    const match = citation.replaceAll("\\", "/").match(ASK_CITATION);
    return match ? askModuleIds(match[1]) : [];
  });
  return Array.from(new Set([...direct, ...indirect]));
}
