// packetTable.ts -- reads the retired-figures table out of docs/JOB_EVIDENCE_PACKET.md
// section 4 at build time, so the retraction page renders the packet verbatim and can
// never drift from it. Build-time only (node:fs); the page is a server component.
import { readFileSync } from "node:fs";
import { join } from "node:path";

export type PacketRow = {
  claim: string;
  why: string;
  sayInstead: string;
  /** "Retracted" when the row carries one of the six retracted figures, else "Retired". */
  status: "Retracted" | "Retired";
  /** First dated note in the row (added / AMENDED / CORRECTED / measured ... YYYY-MM-DD), else null. */
  date: string | null;
};

// The six retracted figures (.claude/rules/no-edge-claims.md); 0.119 also matches 0.1191.
export const RETRACTED_FIGURE = /18\.38|0\.119|\+54|54\.57|78\.11|8\.94/;

export const PACKET_PATH = join(process.cwd(), "..", "docs", "JOB_EVIDENCE_PACKET.md");

/** Parse section 4's markdown table; null when the packet or the table is missing. */
export function parsePacketTable(md: string): PacketRow[] | null {
  const start = md.indexOf("## 4.");
  if (start < 0) return null;
  const next = md.indexOf("\n## ", start + 5);
  const section = md.slice(start, next < 0 ? undefined : next);
  const lines = section.split(/\r?\n/).filter((l) => l.startsWith("|"));
  const rows = lines.slice(2); // header + separator
  const out: PacketRow[] = [];
  for (const line of rows) {
    const cells = line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
    if (cells.length !== 3) continue;
    const [claim, why, sayInstead] = cells;
    const dated = /(?:added|AMENDED|CORRECTED|route,)\s+(\d{4}-\d{2}-\d{2})/.exec(`${claim} ${why}`);
    out.push({
      claim,
      why,
      sayInstead,
      status: RETRACTED_FIGURE.test(claim) ? "Retracted" : "Retired",
      date: dated ? dated[1] : null,
    });
  }
  return out.length ? out : null;
}

export function loadPacketTable(): PacketRow[] | null {
  try {
    return parsePacketTable(readFileSync(PACKET_PATH, "utf-8"));
  } catch {
    return null;
  }
}
