// betdesc.ts -- human-readable bet descriptions + the Kalshi (KX) ticker humanizer.
//
// Two pure formatting helpers used at EVERY bet-render site:
//   humanizeMatchup(s)  -- NEVER shows a raw KX ticker. Decodes
//                          KXMLBGAME-26JUL181510CINCOL -> "CIN @ COL"; falls back
//                          to "<AWAY> @ <HOME>" when only the trailing codes parse,
//                          else "Kalshi market". Non-KX strings pass through. Also
//                          unwraps "sport|matchup|timestamp" composite ids.
//   describeBet(row)    -- full "what IS this bet" string: props ->
//                          "Ildemaro Vargas UNDER 0.5 Hits"; moneyline -> "<TEAM> ML"
//                          (team named from the matchup when derivable); totals ->
//                          "OVER 8.5"; spread -> "COL -1.5". describeBetShort for
//                          tight table cells (last-name props).
//
// Pure functions only -- no data fetch, no React. ASCII only; no $ / edge tokens.

export interface BetDescFields {
  market_type?: string | null;
  market?: string | null; // composite deriv key (total_10.5_over / spread_1.5_home)
  side?: string | null;
  line?: number | null;
  prop_player?: string | null;
  prop_stat?: string | null;
  prop_side?: string | null;
  matchup?: string | null;
  taken_book?: string | null;
}

// --- KX ticker handling ----------------------------------------------------

function isKxTicker(s: string): boolean {
  return /^KX[A-Z0-9]/.test(s) && !/\s/.test(s);
}

// KX<LEAGUE>GAME-<YY><MON><DD><HHMM><AWAY3><HOME3>
//   KXMLBGAME-26JUL181510CINCOL -> "CIN @ COL"   (26 JUL 18, 15:10, CIN@COL)
// After "GAME-": YY(2) + MON(3 letters) + DDHHMM(6 digits) + AWAY3 + HOME3.
function decodeKx(t: string): string {
  // GAME/TOTAL/SPREAD series all share <date><HHMM?><teamblob> tails; time is
  // optional (some tickers omit it) and team codes are 2-3 letters each, so
  // the blob is 4-6 letters. 6 letters -> unambiguous 3+3; other lengths are
  // ambiguous (LADAL = LA+DAL or LAD+AL) -> show the raw blob rather than
  // guess wrong or hide behind "Kalshi market".
  const m = t.match(/-\d{2}[A-Z]{3}\d{2,6}([A-Z]{4,6})$/);
  if (m) {
    const blob = m[1];
    if (blob.length === 6) return `${blob.slice(0, 3)} @ ${blob.slice(3)}`;
    return blob;
  }
  // Unknown KX shape: salvage an exactly-6-letter tail as AWAY3+HOME3.
  const tail = t.match(/([A-Z]{3})([A-Z]{3})$/);
  if (tail) return `${tail[1]} @ ${tail[2]}`;
  return "Kalshi market";
}

export function humanizeMatchup(s: string | null | undefined): string {
  if (s == null) return "";
  const raw = String(s).trim();
  if (raw === "") return "";

  // Composite "sport|matchup|timestamp" (or a bet_id): pull the matchup segment.
  if (raw.includes("|")) {
    const parts = raw.split("|").map((p) => p.trim()).filter(Boolean);
    for (const p of parts) {
      if (/\s(?:@|vs\.?)\s/i.test(p) || isKxTicker(p)) return humanizeMatchup(p);
    }
    return parts[1] ?? parts[0] ?? raw;
  }

  if (isKxTicker(raw)) return decodeKx(raw);
  return raw; // non-KX passes through unchanged
}

// --- team extraction from a (humanized) matchup ----------------------------

function teamsFromMatchup(
  matchup?: string | null,
): { away: string; home: string } | null {
  const h = humanizeMatchup(matchup);
  const m = h.match(/^(.+?)\s+(?:@|vs\.?)\s+(.+)$/i);
  if (!m) return null;
  return { away: m[1].trim(), home: m[2].trim() };
}

function sideToTeam(
  side: string | null | undefined,
  matchup?: string | null,
): string | null {
  const t = teamsFromMatchup(matchup);
  if (!t) return null;
  const s = (side ?? "").toLowerCase();
  if (s.includes("home")) return t.home;
  if (s.includes("away")) return t.away;
  return null;
}

// --- formatting helpers ----------------------------------------------------

function titleCase(s: string): string {
  return s
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

function signedLine(line: number): string {
  return `${line > 0 ? "+" : ""}${line}`;
}

function lastName(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? parts[parts.length - 1] : name.trim();
}

const TOTAL_MARKETS = /^(total|totals|over_?under|ou|game_total)$/i;
const SPREAD_MARKETS = /^(spread|spreads|handicap|run_?line|puck_?line|ats)$/i;
const ML_MARKETS = /^(moneyline|money_?line|ml|h2h|win|win_home|win_away)$/i;

export function isProp(row: BetDescFields): boolean {
  return /prop/i.test(row.market_type ?? "") || row.prop_player != null;
}

function propLabel(row: BetDescFields, short: boolean): string {
  const rawPlayer = row.prop_player?.trim() ?? "";
  const player = short && rawPlayer ? lastName(rawPlayer) : rawPlayer;
  const side = (row.prop_side ?? row.side ?? "").toUpperCase();
  const stat = row.prop_stat ? titleCase(row.prop_stat) : "";
  const parts = [
    player,
    side,
    row.line != null ? String(row.line) : "",
    stat,
  ].filter(Boolean);
  return parts.length ? parts.join(" ") : "prop";
}

// --- describeBet -----------------------------------------------------------

export function describeBet(row: BetDescFields): string {
  let mt = (row.market_type ?? "").toLowerCase();
  // In-play derivative rows encode everything in a composite market key
  // (total_10.5_over / spread_1.5_home) with side kept as home/away
  // bookkeeping -- normalize to the totals/spread paths instead of letting
  // the home/away side masquerade as a moneyline.
  const comp = ((row as { market?: string | null }).market ?? row.market_type ?? "")
    .toLowerCase()
    .match(/^(total|spread)_([\d.]+)_([a-z]+)$/);
  if (comp) {
    // Run-line convention: the home side lays the line (home -1.5), the away
    // side takes it (+1.5); totals lines are unsigned.
    const ln = Number(comp[2]);
    const signed = comp[1] === "spread" && comp[3] === "home" ? -ln : ln;
    row = { ...row, line: signed, side: comp[3] };
    mt = comp[1];
  }

  // Player prop -> "Ildemaro Vargas UNDER 0.5 Hits"
  if (isProp(row)) return propLabel(row, false);

  // Totals -> "OVER 8.5" / "UNDER 8.5"
  if (TOTAL_MARKETS.test(mt)) {
    const side = (row.side ?? "").toUpperCase() || "TOTAL";
    return row.line != null ? `${side} ${row.line}` : side;
  }

  // Spread / handicap -> "COL -1.5" (team when derivable) else "-1.5"
  if (SPREAD_MARKETS.test(mt)) {
    const team = sideToTeam(row.side, row.matchup);
    const ln = row.line != null ? signedLine(row.line) : "";
    return [team, ln].filter(Boolean).join(" ") || (row.side ?? "spread");
  }

  // Moneyline -> "<TEAM> ML" (win_home/win_away encode the side in market_type)
  const sideLooksMl = /^(home|away|win_home|win_away)$/i.test(row.side ?? "");
  if (ML_MARKETS.test(mt) || sideLooksMl) {
    let mlSide = row.side ?? "";
    if (/win_home/i.test(mt)) mlSide = "home";
    else if (/win_away/i.test(mt)) mlSide = "away";
    const team =
      sideToTeam(mlSide, row.matchup) ??
      // side may already be a team abbrev rather than home/away
      (mlSide && !/^(home|away)$/i.test(mlSide) ? mlSide : null);
    return `${team ?? (mlSide.toUpperCase() || "?")} ML`;
  }

  // Fallback: market + side, humanized -- never a bare opaque "prop away".
  const label = [row.market_type, row.side].filter(Boolean).join(" ").trim();
  return label || "bet";
}

// Tight-cell variant: props abbreviate to last name; everything else identical.
export function describeBetShort(row: BetDescFields): string {
  if (isProp(row)) return propLabel(row, true);
  return describeBet(row);
}
