import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const FORBIDDEN = /\b(edge|profit|roi|dollar|bet|wager|bankroll)\b/gi;
const SOURCE_ROOTS = ["app/(analytics)", "components/analytics", "lib/analytics"];
const RETRACTION_TABLE = "app/(analytics)/analytics/findings/retraction/page.tsx";

function sourceFiles(root, directory) {
  const current = join(root, directory);
  if (!existsSync(current)) return [];
  return readdirSync(current, { withFileTypes: true }).flatMap((entry) => {
    const path = join(current, entry.name);
    if (entry.isDirectory()) return sourceFiles(root, join(directory, entry.name));
    return /\.(tsx|ts)$/.test(entry.name) && !/\.test\.(tsx|ts)$/.test(entry.name) ? [path] : [];
  });
}

function lineAt(source, index) {
  return source.slice(0, index).split("\n").length;
}

function hasForbiddenToken(value) {
  FORBIDDEN.lastIndex = 0;
  return FORBIDDEN.test(value);
}

function permittedRetractionFigure(path, source, index) {
  if (path !== RETRACTION_TABLE) return false;
  const line = source.slice(source.lastIndexOf("\n", index) + 1, source.indexOf("\n", index));
  return /^\s*retracted:\s*/.test(line);
}

function withoutComments(source) {
  let result = "";
  let quote = "";
  for (let index = 0; index < source.length; index += 1) {
    const current = source[index];
    if (quote) {
      if (quote === "`" && current === "/" && source[index + 1] === "*") {
        const end = source.indexOf("*/", index + 2);
        const comment = source.slice(index, end === -1 ? source.length : end + 2);
        result += comment.replace(/[^\n]/g, " ");
        index += comment.length - 1;
        continue;
      }
      result += current;
      if (current === "\\") result += source[++index] || "";
      else if (current === quote) quote = "";
      continue;
    }
    if (current === "\"" || current === "'" || current === "`") {
      quote = current;
      result += current;
      continue;
    }
    if (current === "/" && source[index + 1] === "/") {
      const end = source.indexOf("\n", index + 2);
      const comment = source.slice(index, end === -1 ? source.length : end);
      result += comment.replace(/[^\n]/g, " ");
      index += comment.length - 1;
      continue;
    }
    if (current === "/" && source[index + 1] === "*") {
      const end = source.indexOf("*/", index + 2);
      const comment = source.slice(index, end === -1 ? source.length : end + 2);
      result += comment.replace(/[^\n]/g, " ");
      index += comment.length - 1;
      continue;
    }
    result += current;
  }
  return result;
}

function stringLiteralFindings(path, source) {
  const findings = [];
  const code = withoutComments(source);
  for (let index = 0; index < code.length; index += 1) {
    const quote = code[index];
    if (quote !== "\"" && quote !== "'" && quote !== "`") continue;
    let end = index + 1;
    while (end < code.length) {
      if (code[end] === "\\") {
        end += 2;
      } else if (code[end] === quote) {
        end += 1;
        break;
      } else {
        end += 1;
      }
    }
    const literal = code.slice(index, end);
    if (!permittedRetractionFigure(path, source, index) && hasForbiddenToken(literal)) {
      findings.push({ file: path, line: lineAt(source, index), text: literal });
    }
    index = end - 1;
  }
  for (const match of code.matchAll(/>([^<>{}]+)</g)) {
    const index = (match.index ?? 0) + 1;
    if (hasForbiddenToken(match[1])) findings.push({ file: path, line: lineAt(source, index), text: match[1] });
  }
  return findings;
}

export function scanAnalyticsCopy(root = process.cwd()) {
  return SOURCE_ROOTS.flatMap((directory) => sourceFiles(root, directory)).flatMap((absolute) => {
    const path = relative(root, absolute).replaceAll("\\", "/");
    const source = readFileSync(absolute, "utf8");
    return stringLiteralFindings(path, source);
  });
}

const isEntrypoint = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isEntrypoint) {
  const findings = scanAnalyticsCopy();
  for (const finding of findings) console.error(`${finding.file}:${finding.line}`);
  if (findings.length) process.exitCode = 1;
}
