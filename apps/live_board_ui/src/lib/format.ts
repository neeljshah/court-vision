import type { BoardRow, GameState } from "@/types/board";

/** Round a 0..1 (or 0..100) probability to an integer percent, or null. */
export function pct(x: number | null | undefined): number | null {
  if (x === null || x === undefined || Number.isNaN(x)) return null;
  const v = x <= 1 ? x * 100 : x;
  return Math.round(v);
}

/** Format an over/under total to one decimal, or an em dash. */
export function fmtTotal(t: number | null | undefined): string {
  if (t === null || t === undefined || Number.isNaN(t)) return "--";
  return Number(t).toFixed(1);
}

/** True when a value is a usable number (int or numeric string). */
export function isNum(v: unknown): boolean {
  return (
    typeof v === "number" ||
    (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v)))
  );
}

/** Localized short date/time for an ISO string; falls back to the raw input. */
export function localTime(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/** Localized time-of-day only (for the "updated" stamp). */
export function localClock(iso: string | null | undefined): string {
  if (!iso) return new Date().toLocaleTimeString();
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  } catch {
    return iso;
  }
}

/** Compare tennis set-strings ("6 4 7") -> who took more sets. */
export function setsWon(
  awayStr: unknown,
  homeStr: unknown,
): "home" | "away" | null {
  if (typeof awayStr !== "string" || typeof homeStr !== "string") return null;
  const ap = awayStr.trim().split(/\s+/);
  const hp = homeStr.trim().split(/\s+/);
  const n = Math.min(ap.length, hp.length);
  let aw = 0;
  let hw = 0;
  for (let i = 0; i < n; i++) {
    const av = Number(ap[i]);
    const hv = Number(hp[i]);
    if (Number.isNaN(av) || Number.isNaN(hv)) continue;
    if (av > hv) aw++;
    else if (hv > av) hw++;
  }
  if (aw > hw) return "away";
  if (hw > aw) return "home";
  return null;
}

/** Winner side of a FINISHED row: 'home' | 'away' | null (tie/undecidable). */
export function winnerSide(r: BoardRow): "home" | "away" | null {
  if (r.state !== "post") return null;
  const a = r.away_score;
  const h = r.home_score;
  if (isNum(a) && isNum(h)) {
    const na = Number(a);
    const nh = Number(h);
    if (nh > na) return "home";
    if (na > nh) return "away";
    return null;
  }
  return setsWon(a, h);
}

/** Sort/group rank: live first, then upcoming, then finished. */
export function stateRank(s: GameState): number {
  return s === "in" ? 0 : s === "post" ? 2 : 1;
}

/** Rows we actually have a prediction for float above score-only rows. */
export function hasPrediction(r: BoardRow): boolean {
  return Boolean(r.source && r.source !== "unavailable");
}

/**
 * Canonical board ordering: live -> upcoming -> finished; within a group,
 * predicted rows above score-only, then by start time ascending.
 */
export function sortRows(rows: BoardRow[]): BoardRow[] {
  return rows.slice().sort((a, b) => {
    const ra = stateRank(a.state);
    const rb = stateRank(b.state);
    if (ra !== rb) return ra - rb;
    const pa = hasPrediction(a) ? 0 : 1;
    const pb = hasPrediction(b) ? 0 : 1;
    if (pa !== pb) return pa - pb;
    const ta = a.start_time ? Date.parse(a.start_time) : 0;
    const tb = b.start_time ? Date.parse(b.start_time) : 0;
    return (ta || 0) - (tb || 0);
  });
}
