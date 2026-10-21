// /desk -- the Record hub (template T6): the three dates, a status card, the sealed
// scoreboard folded to one row per (sport, arm), coverage, refusals, the
// qualification census summary, the night receipts on GitHub, and what this is not.
// Build-time read of webapp/public/data/desk/latest.json via desk.server plus the
// committed uptime receipt. PAPER ONLY: counts and losses, never a money figure.

import Link from "next/link";
import { loadDesk, refusalsFor } from "@/lib/desk.server";
import { DeskShell, NotAvailable, Section, T } from "@/components/desk/DeskShell";
import { ScoreboardCompact } from "@/components/desk/ScoreboardCompact";
import { StatusCard, CensusSummary, DeskNotClaimed } from "@/components/desk/DeskStatus";
import { CENSUS, CENSUS_SRC, ghBlob, loadUptime } from "@/components/desk/deskExtras.server";
import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo/meta";

export const metadata: Metadata = pageMeta("/desk/", {
  title: "Paper desk record",
  description: "Paper only: simulated maker quotes on the recorded Kalshi tape; nights, scoreboard cells, coverage. Not a verdict.",
});

const SRC = "docs/evidence/forward";

export default function DeskRecordPage() {
  const desk = loadDesk();
  const uptime = loadUptime();
  const rec = desk?.record ?? null;
  const sb = desk?.scoreboard ?? null;
  const cov = desk?.coverage ?? null;
  const nights = [...(desk?.health?.nights ?? [])].reverse();
  const refusalRows: [string, string, number][] = [
    ...Object.entries(sb?.refusal_counts ?? {}).map(([k, v]) => ["scoreboard", k, v] as [string, string, number]),
    ...Object.entries(cov?.refusals ?? {}).map(([k, v]) => ["coverage", k, v] as [string, string, number]),
  ];

  return (
    <DeskShell desk={desk} title="Paper desk record" active="/desk">
      <Section title="Status" asOf={desk?.date} source="webapp/public/data/desk/latest.json">
        <StatusCard desk={desk} uptime={uptime} />
      </Section>

      <Section title="In-game scoreboard, one row per sport and arm" asOf={sb?.date} verdict="INSUFFICIENT"
        source={sb ? `${SRC}/scoreboard/${sb.date}.json` : null}>
        {sb ? <ScoreboardCompact sb={sb} arms={desk?.models?.scoreboard_arms ?? null} />
          : <NotAvailable refusals={refusalsFor(desk, "scoreboard")} />}
      </Section>

      <Section title="Coverage per sport" asOf={cov?.date} source={cov ? `${SRC}/coverage/${cov.date}.json` : null}>
        {cov ? (
          <>
            <T head={["sport", "listed", "selected", "served", "qualified PASS / FAIL", "scored ticks (arm A)"]}
              rows={cov.sports.map((s) => [s.sport, s.listed ?? "-", s.selected ?? "-", s.served ?? "-",
                s.qualified ? `${s.qualified.PASS ?? "-"} / ${s.qualified.FAIL ?? "-"}` : "-",
                s.scored_ticks?.A ?? "-"])} />
            <p className="px-3 py-2 text-xs text-faint">{cov.listed_definition}</p>
          </>
        ) : <NotAvailable refusals={refusalsFor(desk, "coverage")} />}
      </Section>

      <Section title="Qualification census: why no game qualifies" asOf={CENSUS.asOf} source={CENSUS_SRC}
        verdict="INSUFFICIENT">
        <CensusSummary />
      </Section>

      <Section title="Ledger per night (counts only)" asOf={desk?.date} source={`${SRC}/paper_result/LEDGER.jsonl`}>
        {rec ? (
          <T head={["night", "quote life s", "fills", "settled", "unsettled", "contracts", "note"]}
            rows={rec.ledger.map((r) => [r.date, r.quote_life_s ?? "-", r.fills ?? "-",
              r.settled_fills ?? "-", r.unsettled_fills ?? "-", r.contracts ?? "-", r.note ?? ""])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "record")} />}
        <p className="px-3 py-2 text-xs text-muted-foreground">
          The fills themselves are on the <Link href="/paper-trading/" className="underline">paper record</Link>.
        </p>
      </Section>

      <Section title="Refusals in this export" asOf={desk?.date} source="webapp/public/data/desk/latest.json">
        <p className="px-3 pt-2 text-xs text-muted-foreground">
          A refusal is a tick, game or section the scorer declined to use, with the receipt&apos;s reason code.
          Refused rows are counted, never dropped silently.
        </p>
        {refusalRows.length ? <T head={["stage", "reason code", "count"]} rows={refusalRows} />
          : <p className="px-3 py-2 text-xs">No scoreboard or coverage refusals in this export.</p>}
        {desk && desk.refusals.length > 0 && <NotAvailable refusals={desk.refusals} />}
      </Section>

      <Section title="Night receipts on GitHub" asOf={desk?.date} source={`${SRC}/nights/`}>
        {nights.length ? (
          <ul className="grid gap-1 px-3 py-2 text-xs sm:grid-cols-2" data-testid="night-receipt-links">
            {nights.map((n) => (
              <li key={n.date}>
                <a className="font-data underline" href={ghBlob(`${SRC}/nights/${n.date}.json`)}>nights/{n.date}.json</a>{" "}
                <span className="text-muted-foreground">{n.status ?? "status not stated"}</span>
              </li>
            ))}
          </ul>
        ) : <NotAvailable refusals={refusalsFor(desk, "health")} />}
      </Section>

      <DeskNotClaimed />
    </DeskShell>
  );
}
