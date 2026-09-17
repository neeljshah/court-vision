#!/usr/bin/env node
// Publication gate for every committed paper. Runtime loading remains forgiving; this
// script is deliberately strict so an omitted paper cannot pass unnoticed.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();
const data = join(root, "public", "data");
const papers = join(data, "papers");
const forbidden = /(?<![A-Za-z0-9_])(edge|edges|bet|bets|betting|bettor|bettors|bookmaker|bookmakers|sportsbook|profit|profits|profitable|roi|wager|wagers|wagering|bankroll|bankrolls|payout|payouts|odds boost|financial returns?|betting returns?|dollar)(?![A-Za-z0-9])/i;
const isBag = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const owns = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

function names(directory) {
  return existsSync(directory) ? readdirSync(directory).filter((entry) => entry.endsWith(".json")) : [];
}

const showcase = new Set(names(join(data, "showcase")));
const insights = new Set(names(join(data, "insights")));
const artifacts = new Set([...showcase, ...insights]);
const paperIds = new Set(names(papers).flatMap((entry) => {
  try {
    const paper = JSON.parse(readFileSync(join(papers, entry), "utf8"));
    return typeof paper.slug === "string" ? [paper.slug] : [];
  } catch { return []; }
}));

function sourceIds(pattern, files) {
  const ids = new Set();
  for (const file of files) {
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(pattern)) ids.add(match[1]);
  }
  return ids;
}

const analytics = join(root, "lib", "analytics");
const researchFiles = readdirSync(analytics).filter((entry) => /^research.*\.ts$/.test(entry)).map((entry) => join(analytics, entry));
const analysisIds = sourceIds(/\bid:\s*["']([^"']+)["']/g, researchFiles);
const findingIds = sourceIds(/define\(["']([^"']+)["']/g, [join(analytics, "findingsIndex.ts")]);
const inspectorIds = sourceIds(/\bid:\s*["']([^"']+)["']/g, [join(analytics, "analysisDestinations.ts")]);

function segments(path) {
  if (typeof path !== "string" || !path) return null;
  const output = [];
  const parts = [];
  let part = "", bracket = false;
  for (const character of path) {
    if (character === "[") { if (bracket) return null; bracket = true; }
    if (character === "]") { if (!bracket) return null; bracket = false; }
    if (character === "." && !bracket) { if (!part) return null; parts.push(part); part = ""; }
    else part += character;
  }
  if (bracket || !part) return null;
  parts.push(part);
  for (const segment of parts) {
    const match = /^([A-Za-z0-9_$-]+)((?:\[[^\]]*\])*)$/.exec(segment);
    if (!match) return null;
    const selectors = [...match[2].matchAll(/\[([^\]]*)\]/g)].map((entry) => entry[1]);
    if (selectors.some((selector) => selector !== "" && !/^\d+$/.test(selector)
      && !selector.split(",").every((condition) => /^[A-Za-z0-9_$-]+=[A-Za-z0-9_$+().:/|-]+$/.test(condition))
      && !/^[A-Za-z0-9_$+().:/|-]+$/.test(selector))) return null;
    output.push({ property: match[1], selectors });
  }
  return output;
}

function select(values, selector) {
  if (selector === "") return values.flatMap((value) => Array.isArray(value) ? value : []);
  if (/^\d+$/.test(selector)) {
    const index = Number(selector);
    return values.flatMap((value) => Array.isArray(value) && owns(value, String(index)) ? [value[index]] : []);
  }
  const separator = selector.indexOf("=");
  if (separator > 0) {
    const conditions = selector.split(",").map((part) => {
      const position = part.indexOf("=");
      return position > 0 ? [part.slice(0, position), part.slice(position + 1)] : null;
    });
    if (conditions.some((condition) => !condition || !condition[1])) return [];
    return values.flatMap((value) => Array.isArray(value) ? value.filter((entry) => isBag(entry) && conditions.every((condition) => owns(entry, condition[0]) && String(entry[condition[0]]) === condition[1])) : []);
  }
  return values.flatMap((value) => isBag(value) && owns(value, selector) ? [value[selector]] : []);
}

function fieldExists(value, path) {
  const parsed = segments(path);
  if (!parsed) return false;
  let values = [value];
  for (const segment of parsed) {
    values = values.flatMap((entry) => isBag(entry) && owns(entry, segment.property) ? [entry[segment.property]] : []);
    for (const selector of segment.selectors) values = select(values, selector);
    if (!values.length) return false;
  }
  return true;
}

function strings(value, into = []) {
  if (typeof value === "string") into.push(value);
  else if (Array.isArray(value)) value.forEach((entry) => strings(entry, into));
  else if (isBag(value)) Object.values(value).forEach((entry) => strings(entry, into));
  return into;
}

function paperReason(paper) {
  if (!isBag(paper)) return "not a JSON object";
  if (!Array.isArray(paper.sections) || !paper.sections.length) return "sections is empty";
  const sectionIds = new Set();
  for (const section of paper.sections) {
    if (!isBag(section) || typeof section.id !== "string" || !section.id) return "section needs an id";
    if (sectionIds.has(section.id)) return `duplicate section id ${section.id}`;
    sectionIds.add(section.id);
  }
  if (!Array.isArray(paper.evidence) || !paper.evidence.length) return "evidence is empty";
  for (let index = 0; index < paper.evidence.length; index += 1) {
    const entry = paper.evidence[index];
    if (!isBag(entry) || typeof entry.artifact !== "string" || !Array.isArray(entry.fields)) return `evidence[${index}] is malformed`;
    if (!artifacts.has(entry.artifact)) return `evidence[${index}] names ${entry.artifact}, which is not a published artifact`;
    if (entry.path !== undefined && entry.path !== "showcase" && entry.path !== "insights") return `evidence[${index}] path is not recognized`;
    if (entry.dateMeaning !== undefined && !["snapshot", "window", "not-published"].includes(entry.dateMeaning)) return `evidence[${index}] dateMeaning is not recognized`;
    const directory = entry.path || (showcase.has(entry.artifact) ? "showcase" : "insights");
    const source = join(data, directory, entry.artifact);
    let artifact;
    try { artifact = JSON.parse(readFileSync(source, "utf8")); } catch { return `evidence[${index}] artifact ${entry.artifact} is unavailable in ${directory}`; }
    for (const path of entry.fields) if (!fieldExists(artifact, path)) return `evidence[${index}] field path ${path} does not resolve in ${directory}/${entry.artifact}`;
  }
  if (!Array.isArray(paper.related)) return "related must be a list";
  for (const link of paper.related) {
    if (!isBag(link) || typeof link.id !== "string" || typeof link.kind !== "string") return "related entries need a known kind and an id";
    const known = link.kind === "module" ? artifacts.has(`${link.id}.json`)
      : link.kind === "inspector" ? inspectorIds.has(link.id)
        : link.kind === "analysis" ? analysisIds.has(link.id)
          : link.kind === "finding" ? findingIds.has(link.id)
            : link.kind === "paper" ? paperIds.has(link.id) : false;
    if (!known) return `related ${link.kind} ${link.id} is not registered`;
  }
  for (const text of strings(paper)) if (!/^[\x20-\x7E\n\t]*$/.test(text)) return "non-ASCII text";
  for (const text of strings(paper)) if (forbidden.test(text)) return "prohibited vocabulary";
  return null;
}

let failures = 0;
for (const entry of names(papers)) {
  let reason;
  try { reason = paperReason(JSON.parse(readFileSync(join(papers, entry), "utf8"))); } catch { reason = "unparsable JSON"; }
  console.log(`${reason ? "FAIL" : "OK"} ${entry}${reason ? ` -- ${reason}` : ""}`);
  if (reason) failures += 1;
}
if (failures) process.exit(1);
