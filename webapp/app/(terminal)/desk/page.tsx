// /desk -- the paper record: ledger per night (counts only), the in-game
// scoreboard per arm with the venue mid (arm A) as the reference, and coverage.
// Build-time read of webapp/public/data/desk/latest.json via desk.server.

import { loadDesk, refusalsFor, fmt } from "@/lib/desk.server";
import { DeskShell, NotAvailable, Section, T } from "@/components/desk/DeskShell";
import { DeltaBars } from "@/components/charts/DeltaBars";
import { Num } from "@/components/ui/terminal";

export const metadata = {
  title: "Paper desk",
  description: "Paper only, simulated maker quotes on the recorded Kalshi tape; not a verdict.",
};

const SRC = "docs/evidence/forward";

export default function DeskRecordPage() {
  const desk = loadDesk();
  const rec = desk?.record ?? null;
  const sb = desk?.scoreboard ?? null;
  const cov = desk?.coverage ?? null;
  const sports = sb ? Array.from(new Set(sb.rows.map((r) => r.sport))) : [];

  return (
    <DeskShell desk={desk} title="Paper record" active="/desk">
      <Section title="Ledger per night (counts only)" asOf={desk?.date} source={`${SRC}/paper_result/LEDGER.jsonl`}>
        {rec ? (
          <T head={["night", "quote life s", "fills", "settled", "unsettled", "contracts", "note"]}
            rows={rec.ledger.map((r) => [r.date, r.quote_life_s ?? "-", <Num key="f">{r.fills ?? "-"}</Num>,
              r.settled_fills ?? "-", r.unsettled_fills ?? "-", r.contracts ?? "-", r.note ?? ""])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "record")} />}
      </Section>

      <Section title="Fill realism and fills receipts per night" asOf={desk?.date} source={`${SRC}/fill_realism/`}>
        {rec ? (
          <T head={["night", "quotes placed", "fills TTL 30 s", "fills TTL 5 s", "fills rows", "reconciled"]}
            rows={rec.nights.map((n) => [n.date, n.fill_realism?.quotes_placed ?? "not available",
              n.fill_realism?.fills_ttl30 ?? "-", n.fill_realism?.fills_ttl5 ?? "-", n.fills_rows ?? "-",
              n.reconciled ? Object.entries(n.reconciled).map(([k, v]) => `${k}s:${v}`).join(" ") : "-"])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "record")} />}
      </Section>

      <Section title="In-game scoreboard per arm (reference: arm A = venue mid)" asOf={sb?.date}
        source={sb ? `${SRC}/scoreboard/${sb.date}.json` : null}>
        {sb ? (
          <div className="flex flex-col gap-4 py-2">
            <p className="px-3 text-[12px] text-muted-foreground">
              Brier and log loss per arm on the outcome target; the delta column is the arm minus arm A on the
              same segment (negative = lower loss than the mid). Every cell carries its verdict; with few games
              they read INSUFFICIENT. Scope {sb.scope ?? "-"}; {sb.games} games, {sb.ticks} ticks.
            </p>
            {sports.map((s) => (
              <div key={s}>
                <p className="microlabel px-3">{s}</p>
                <T head={["segment", "arm", "Brier", "log loss", "Brier - A", "", "ticks", "games", "verdict"]}
                  rows={sb.rows.filter((r) => r.sport === s && r.target === "outcome").map((r) => [
                    r.segment, r.arm, fmt(r.brier), fmt(r.logloss), fmt(r.brier_minus_A),
                    r.brier_minus_A == null ? (r.reason ?? "") :
                      <DeltaBars key="d" delta={r.brier_minus_A} ci={[r.brier_minus_A, r.brier_minus_A]}
                        verdict={r.verdict ?? "INSUFFICIENT"} />,
                    r.n_ticks ?? "-", r.n_games ?? "-", r.verdict ?? "-"])} />
              </div>
            ))}
            <div className="px-3">
              <p className="microlabel">scoreboard refusal counts</p>
              <p className="font-data text-[11px] text-faint">
                {Object.entries(sb.refusal_counts).map(([k, v]) => `${k}=${v}`).join("  ") || "none"}
              </p>
            </div>
          </div>
        ) : <NotAvailable refusals={refusalsFor(desk, "scoreboard")} />}
      </Section>

      <Section title="Coverage per sport" asOf={cov?.date} source={cov ? `${SRC}/coverage/${cov.date}.json` : null}>
        {cov ? (
          <>
            <T head={["sport", "listed", "selected", "served", "qualified PASS / FAIL", "scored ticks (A)"]}
              rows={cov.sports.map((s) => [s.sport, s.listed ?? "-", s.selected ?? "-", s.served ?? "-",
                s.qualified ? `${s.qualified.PASS ?? "-"} / ${s.qualified.FAIL ?? "-"}` : "-",
                s.scored_ticks?.A ?? "-"])} />
            <p className="px-3 py-2 text-[11px] text-faint">{cov.listed_definition}</p>
          </>
        ) : <NotAvailable refusals={refusalsFor(desk, "coverage")} />}
      </Section>

      <Section title="Refusals in this export" asOf={desk?.date}>
        {desk && desk.refusals.length === 0 ? <p className="px-3 py-2 text-[12px]">none</p> :
          <NotAvailable refusals={desk ? desk.refusals : refusalsFor(null, "desk")} />}
      </Section>
    </DeskShell>
  );
}
