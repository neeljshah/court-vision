// CalibrationVerdictTable -- T2 verdict table (DESIGN_PRINCIPLES section 3): sport x market x
// checkpoint with n games, n rows, Brier model / market / 0.25 baseline, gap with interval and
// the packet verdict. Rows come from docs/evidence/CANONICAL_FIGURES.json, largest n first.
import Link from "next/link";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import { VerdictLabel, type PacketVerdict } from "@/components/evidence";
import type { CanonicalFigure } from "@/lib/canonicalFigures.server";

const f4 = (v: number | undefined) => (v == null ? "not published" : v.toFixed(4));
const s4 = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(4);
/** Display names for the canonical sport ids (shared with CalibrationIntro). */
export const SPORT: Record<string, string> = { mlb: "MLB", nba: "NBA", soccer: "Soccer", soccer_intl: "International soccer" };

/** The packet's licensed in-game sentence for the 227-game Brier pair (docs/JOB_EVIDENCE_PACKET.md). */
export const INGAME_JOIN_CAVEAT = "Measured 2026-09-14 on the 227-game corpus that later failed the join-integrity check; the 178-game segmented revision keeps the verdict BEHIND.";
export const LATENCY_PAPER_HREF = "https://github.com/neeljshah/court-vision/blob/master/docs/papers/INPLAY_LATENCY_2026.md";
/** Soccer in-play row: same corpus as the failed join-integrity check, never re-established. */
export const SOCCER_JOIN_NOTE = "Measured before the join-integrity repair; not re-established after it.";
// Notes keyed by row identity (CANONICAL_FIGURES key), not by n.
const NOTES: Record<string, { id: string; mark: string }> = {
  mlb_ingame_vs_kalshi_mid: { id: "ingame-join-caveat", mark: "*" },
  soccer_ingame_vs_kalshi_mid: { id: "soccer-join-note", mark: "**" },
};

export const isVerdictRow = (f: CanonicalFigure) => f.metric === "Brier" && f.model != null && f.close != null;

export function verdictRows(figs: CanonicalFigure[]): CanonicalFigure[] {
  return figs.filter(isVerdictRow).sort((a, b) => (b.n ?? 0) - (a.n ?? 0));
}

function underpowered(f: CanonicalFigure): boolean {
  return f.verdict === "MATCHES_CLOSE" && f.mde != null && f.ci95 != null && f.ci95[1] - f.ci95[0] > f.mde;
}

export function CalibrationVerdictTable({ figures }: { figures: CanonicalFigure[] }) {
  const rows = verdictRows(figures);
  if (!rows.length) return <p>docs/evidence/CANONICAL_FIGURES.json is not staged on this clone.</p>;
  return (
    <div className="calibration-table-wrap" role="region" aria-label="Verdict table, scrollable" data-scroll-region tabIndex={0}>
      <table className="calibration-table">
        <caption>Model against the market reference, Brier (lower is better)</caption>
        <thead>
          <tr>
            <th>Sport</th><th>Market</th><th>Checkpoint</th><th>Reference</th><th>n games</th><th>n rows</th>
            <th>Brier model</th><th>Brier market</th><th>Brier baseline</th><th>Gap (model minus market), 95% CI</th>
            <th>Verdict</th><th>As of</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((f) => {
            const ingame = f.n_unit === "games";
            // BEHIND (in-play, vs the Kalshi mid) and TRAILS_CLOSE (pregame, vs the devigged close) are
            // both packet words and print verbatim; VerdictLabel throws on anything else.
            const verdict = f.verdict as PacketVerdict;
            return (
              <tr key={f.key} className="metric" data-key={f.key}>
                <td>{SPORT[f.sport] ?? f.sport}</td>
                <td>{f.market}</td>
                <td>{ingame ? "in-play ticks" : "pregame"}</td>
                <td>{ingame ? "Kalshi in-play mid" : `${f.devig ?? ""} devigged close`.trim()}{NOTES[f.key] && <sup data-role="caveat-ref"><a href={`#${NOTES[f.key].id}`} aria-label="Join-integrity caveat">{NOTES[f.key].mark}</a></sup>}</td>
                <td data-role="n">{f.n?.toLocaleString("en-US")}</td>
                <td>{ingame ? "not published" : `${f.n?.toLocaleString("en-US")} (one per game)`}</td>
                <td>{f4(f.model)} <small>(lower is better)</small></td>
                <td>{f4(f.close)}</td>
                <td>0.2500</td>
                <td data-role="interval">
                  {f.gap != null ? s4(f.gap) : "--"}{" "}
                  {f.ci95 ? `[${s4(f.ci95[0])}, ${s4(f.ci95[1])}]` : "no interval"}
                </td>
                <td>
                  <span data-role="verdict"><VerdictLabel verdict={verdict} qualifier={false} /></span>
                  {underpowered(f) && <> <span data-role="qualifier"><VerdictLabel verdict="UNDERPOWERED" qualifier={false} /></span></>}
                </td>
                <td>
                  <span data-role="asof">{f.as_of}</span>
                  <span data-role="receipt">
                    <ReceiptChip sourceArtifact={f.source} asOf={f.as_of} verified="edge_claimed:false"
                      verdict={verdict} n={f.n ?? null} ci={f.ci95 ?? null} />
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {rows.some((f) => f.key === "mlb_ingame_vs_kalshi_mid") && (
        <p id="ingame-join-caveat" data-role="caveat"><small>
          {/* the trailing packet word renders as a VerdictLabel; the text stays the licensed sentence */}
          * {INGAME_JOIN_CAVEAT.replace(/ BEHIND\.$/, " ")}<VerdictLabel verdict="BEHIND" qualifier={false} />. See <Link href="/analytics/findings/ingame-join-integrity/">the join-integrity finding</Link> and{" "}
          <a href={LATENCY_PAPER_HREF}>the in-play latency paper</a>.
        </small></p>
      )}
      {rows.some((f) => f.key === "soccer_ingame_vs_kalshi_mid") && (
        <p id="soccer-join-note" data-role="caveat"><small>** {SOCCER_JOIN_NOTE}</small></p>
      )}
    </div>
  );
}
