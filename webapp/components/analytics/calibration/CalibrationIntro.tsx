// CalibrationIntro -- the calibration page's one-paragraph verdict, generated from the same
// CANONICAL_FIGURES rows as the verdict table so a canonical change can never leave the prose
// stale. Each clause is the home h2 mapping (app/(terminal)/page.tsx): sport, market, the packet
// verdict as a VerdictLabel, and the qualifier the packet attaches (VERDICT_QUALIFIER), e.g.
// "NBA moneyline MATCHES_CLOSE (underpowered)". Clauses that repeat (the two NBA devig variants)
// print once; a devig variant with a different verdict would print as its own clause. A row whose
// 95% interval includes zero prints CANNOT_TELL in prose; its packet word stays in the table cell.
import { Fragment } from "react";
import { Term, VerdictLabel, VERDICT_QUALIFIER, type PacketVerdict } from "@/components/evidence";
import type { CanonicalFigure } from "@/lib/canonicalFigures.server";
import { SPORT, verdictRows } from "./CalibrationVerdictTable";

export type VerdictClause = { key: string; sport: string; market: string; verdict: PacketVerdict; qualifier: string | null; cannotTell: boolean };

export const CANNOT_TELL = "cannot tell (interval includes zero; underpowered)";
const includesZero = (f: CanonicalFigure) => f.ci95 != null && f.ci95[0] <= 0 && f.ci95[1] >= 0;

/** One clause per distinct sport x market x verdict, in the rows' order (largest n first). */
export function verdictClauses(rows: CanonicalFigure[]): VerdictClause[] {
  const seen = new Set<string>();
  const out: VerdictClause[] = [];
  for (const f of rows) {
    const sport = SPORT[f.sport] ?? f.sport;
    const verdict = f.verdict as PacketVerdict;
    const id = `${sport} ${f.market} ${verdict}`;
    if (seen.has(id)) continue;
    seen.add(id);
    out.push({ key: f.key, sport, market: f.market, verdict, qualifier: VERDICT_QUALIFIER[verdict] ?? null, cannotTell: includesZero(f) });
  }
  return out;
}

/** The clause as text: exactly what the home h2 prints for the same row. */
export const clauseText = (c: VerdictClause) =>
  c.cannotTell ? `${c.sport} ${c.market} ${CANNOT_TELL}` : `${c.sport} ${c.market} ${c.verdict}${c.qualifier ? ` (${c.qualifier})` : ""}`;

function Clauses({ rows }: { rows: CanonicalFigure[] }) {
  return (
    <>
      {verdictClauses(rows).map((c, i) => (
        <Fragment key={c.key}>
          {i ? "; " : ""}{c.sport} {c.market}{" "}
          {c.cannotTell ? CANNOT_TELL : <><VerdictLabel verdict={c.verdict} qualifier={false} />{c.qualifier ? ` (${c.qualifier})` : ""}</>}
        </Fragment>
      ))}
    </>
  );
}

export function CalibrationIntro({ figures }: { figures: CanonicalFigure[] }) {
  const rows = verdictRows(figures);
  const pregame = rows.filter((f) => f.n_unit !== "games");
  const inplay = rows.filter((f) => f.n_unit === "games");
  return (
    <p className="calibration-intro" data-testid="calibration-intro">
      Verdict. Pregame vs the <Term id="devigged-close">devigged close</Term>: <Clauses rows={pregame} />.
      {inplay.length ? <> In play: <Clauses rows={inplay} />.</> : null}
      {" "}Every row below is scored by <Term id="brier">Brier score</Term> (lower is better) and shows its n, 95% interval, as-of date and receipt.
    </p>
  );
}
