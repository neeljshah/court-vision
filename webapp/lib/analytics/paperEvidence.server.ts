// Build-time evidence resolution for papers. Kept separate from papers.ts so client
// components can use the paper contract without reaching node:fs.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { validatePaper, type Paper, type PaperEvidence, type PaperReferences } from "./papers";

type Bag = Record<string, unknown>;
type EvidenceDirectory = "showcase" | "insights";
export type ResolvedPaperEvidence = { directory: EvidenceDirectory; file: string; value: unknown };

const root = () => process.cwd();
const isBag = (value: unknown): value is Bag => value !== null && typeof value === "object" && !Array.isArray(value);
const fileName = (artifact: string) => artifact.split(/[\\/]/).pop() || "";

function evidenceFile(artifact: string, directory: EvidenceDirectory): string {
  return join(root(), "public", "data", directory, artifact);
}

/** Resolves a basename to one public data file; showcase wins when both copies exist. */
export function resolveEvidenceArtifact(entry: PaperEvidence): ResolvedPaperEvidence | null {
  if (fileName(entry.artifact) !== entry.artifact) return null;
  const candidates: EvidenceDirectory[] = entry.path ? [entry.path] : ["showcase", "insights"];
  for (const directory of candidates) {
    const file = evidenceFile(entry.artifact, directory);
    if (!existsSync(file)) continue;
    try {
      return { directory, file, value: JSON.parse(readFileSync(file, "utf8")) };
    } catch {
      return null;
    }
  }
  return null;
}

type Segment = { property: string | null; selectors: string[] };

function segments(path: string): Segment[] | null {
  if (!path || path.includes("<")) return null;
  const output: Segment[] = [];
  let position = 0;
  while (position < path.length) {
    if (output.length) {
      if (path[position] !== ".") return null;
      position += 1;
    }
    const property = /^[A-Za-z0-9_$-]+/.exec(path.slice(position))?.[0] || null;
    if (property) position += property.length;
    else if (path[position] !== "[") return null;
    const selectors: string[] = [];
    while (path[position] === "[") {
      const end = path.indexOf("]", position + 1);
      if (end < 0) return null;
      const selector = path.slice(position + 1, end);
      if (selector.startsWith('"')) {
        try { JSON.parse(selector); } catch { return null; }
      }
      selectors.push(selector);
      position = end + 1;
    }
    if (!property && !selectors.length) return null;
    output.push({ property, selectors });
  }
  return output;
}

const owns = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);

function select(values: unknown[], selector: string): unknown[] {
  if (selector === "") return values.flatMap((value) => Array.isArray(value) ? value : isBag(value) ? Object.values(value) : []);
  if (selector.startsWith('"')) {
    const key = JSON.parse(selector) as string;
    return values.flatMap((value) => isBag(value) && owns(value, key) ? [value[key]] : []);
  }
  if (/^\d+$/.test(selector)) {
    const index = Number(selector);
    return values.flatMap((value) => Array.isArray(value) && index < value.length ? [value[index]] : []);
  }
  const separator = selector.indexOf("=");
  if (separator > 0) {
    const conditions = selector.split(",").map((part) => {
      const position = part.indexOf("=");
      return position > 0 ? [part.slice(0, position), part.slice(position + 1)] : null;
    });
    if (conditions.some((condition) => !condition || !condition[1])) return [];
    return values.flatMap((value) => Array.isArray(value)
      ? value.filter((entry) => isBag(entry) && conditions.every((condition) => owns(entry, condition![0]) && String(entry[condition![0]]) === condition![1]))
      : []);
  }
  return values.flatMap((value) => isBag(value) && owns(value, selector) ? [value[selector]] : []);
}

/** Supports dotted keys, [] wildcards, [key=value] array selectors, and keyed brackets. */
export function fieldPathExists(value: unknown, path: string): boolean {
  const parsed = segments(path);
  if (!parsed) return false;
  let values: unknown[] = [value];
  for (const segment of parsed) {
    const property = segment.property;
    if (property) values = values.flatMap((entry) => isBag(entry) && owns(entry, property) ? [entry[property]] : []);
    for (const selector of segment.selectors) values = select(values, selector);
    if (!values.length) return false;
  }
  return values.length > 0;
}

function fieldPathProblem(path: string): string | null {
  if (path.includes("<")) return "contains an unsupported placeholder; use [] wildcard syntax";
  return segments(path) ? null : "is not a valid field path";
}

/** Returns the first structural or evidence-resolution problem for a paper. */
export function validatePaperEvidence(
  value: unknown,
  artifacts: ReadonlySet<string>,
  references?: PaperReferences,
): string | null {
  const contract = validatePaper(value, artifacts, references);
  if (contract) return contract;
  const paper = value as Paper;
  for (let index = 0; index < paper.evidence.length; index += 1) {
    const entry = paper.evidence[index];
    const resolved = resolveEvidenceArtifact(entry);
    if (!resolved) return `evidence[${index}] artifact ${entry.artifact} is unavailable in ${entry.path || "showcase or insights"}`;
    for (const path of entry.fields) {
      const problem = fieldPathProblem(path);
      if (problem) return `evidence[${index}] field path ${path} ${problem}`;
      if (!fieldPathExists(resolved.value, path)) {
        return `evidence[${index}] field path ${path} does not resolve in ${resolved.directory}/${entry.artifact}`;
      }
    }
  }
  return null;
}
