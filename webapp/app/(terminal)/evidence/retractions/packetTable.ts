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

// Render-time presentation filter. The packet is the truth source and is never edited for the
// site; these rules only drop its interview-coaching sentences, keep return figures out of the
// replacement column, and collapse the long tracking row to its three load-bearing sentences.
const CALIBRATION_STATEMENT =
  "The pregame model trails the devigged close on MLB moneyline and soccer O/U 2.5; on NBA moneyline the interval includes zero, so we cannot tell.";
// "Apply as ... hire." addresses a hirer; the discipline quote ends at "its fix".
const COACHING = [/Apply as an [^.]*hire\.\s*/g, /\s*-- that is the discipline, not an embarrassment/g];
const INPLAY_STATEMENT =
  "In play the model trails the Kalshi mid; the L5-proxy backtest is a model-quality ceiling, never a realized result.";
const RETURN_FIGURE = /[~+-]\s?-?\d+(?:\.\d+)?%|break-even|\bROI\b|P&L|hits \d+%/;
const TRACKING_WHY =
  "Measured on the research route, 2026-09-04, not asserted: on one WNBA clip through a validated homography, 10.5 pct of on-court same-ID steps are physically impossible (G267/G270). " +
  "Only about one retained detection in five sits on a player's feet (G287), detector recall is not established, and the impossible-step rate has no established mechanism. " +
  "Scope is one clip, one camera shot and one labeller; the full measurement record with receipts G267 to G298 is in section 4 of the packet.";

export function presentRow(r: PacketRow): PacketRow {
  let { why, sayInstead } = r;
  for (const re of COACHING) sayInstead = sayInstead.replace(re, "");
  why = why.replace(/\s*At real odds [^;]*;[^%]*%\./, "");
  if (RETURN_FIGURE.test(sayInstead)) sayInstead = `"${/in-play/i.test(r.claim) ? INPLAY_STATEMENT : CALIBRATION_STATEMENT}"`;
  if (why.length > 3000) {
    why = TRACKING_WHY;
    sayInstead = sayInstead.replace(/^\s*"?([^.]*\.).*$/s, '"$1"');
  }
  return { ...r, why, sayInstead: sayInstead.trim() };
}

export function loadPacketTable(): PacketRow[] | null {
  try {
    return parsePacketTable(readFileSync(PACKET_PATH, "utf-8"))?.map(presentRow) ?? null;
  } catch {
    return null;
  }
}
