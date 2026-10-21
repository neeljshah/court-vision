// /desk/health -- desk operations in one place (the retired /system, /progress and
// /models pages fold here): capture heartbeats from the export, the host uptime
// table, the check_all count, open issues from the newest issue ledger, nightly
// steps, and the sources read. Build-time reads only; every age is measured
// against the export's own stamp, never the viewer clock. PAPER ONLY.

import { loadDesk, refusalsFor, fmt } from "@/lib/desk.server";
import { DeskShell, NotAvailable, Section, T } from "@/components/desk/DeskShell";
import { heartbeats } from "@/components/desk/DeskStatus";
import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo/meta";
import {
  CHECK_ALL_SRC, UPTIME_SRC, ghBlob, loadChecks, loadIssues, loadUptime,
} from "@/components/desk/deskExtras.server";

export const metadata: Metadata = pageMeta("/desk/health/", {
  title: "Desk health",
  description: "Paper only: capture heartbeats, host uptime, nightly steps, open issues and self-checks.",
});

const EXPORT = "webapp/public/data/desk/latest.json";
const counts = (o: Record<string, number> | null | undefined) =>
  Object.entries(o ?? {}).map(([k, v]) => `${k} ${v}`).join(", ") || "none";

function Reason({ children }: { children: string }) {
  return <p className="px-3 py-2 text-xs text-stale">{children}</p>;
}

export default function DeskHealthPage() {
  const desk = loadDesk();
  const h = desk?.health ?? null;
  const nights = h?.nights ?? [];
  const beats = heartbeats(desk);
  const uptime = loadUptime();
  const issues = loadIssues();
  const checks = loadChecks();
  const recorderRefusal = desk?.refusals.find((r) => r.section === "ingame");

  return (
    <DeskShell desk={desk} title="Desk health" active="/desk/health">
      <Section title="Capture supervisors: last heartbeat" asOf={desk?.generated_at_utc} source={EXPORT}>
        {beats.length ? (
          <T head={["process", "decision", "reason", "at (UTC)", "minutes before the export"]}
            rows={beats.map((b) => [b.key, b.decision, b.reason, b.ts ?? "not stated", b.ageMin ?? "-"])} />
        ) : <Reason>The desk export carries no capture status, so no heartbeat can be shown.</Reason>}
        <p className="px-3 py-2 text-xs text-muted-foreground">
          Live shadow recorder:{" "}
          {recorderRefusal
            ? `no heartbeat in this export, because ${recorderRefusal.reason}.`
            : "the export carries its in-game section; see the in-game page."}
        </p>
      </Section>

      <Section title="Host uptime per day" asOf={uptime?.asOf} source={UPTIME_SRC}>
        {uptime ? (
          <>
            <p className="px-3 py-2 text-xs text-muted-foreground">
              Window {uptime.window} ({uptime.days} days): {uptime.scored} scored nights ({uptime.complete} COMPLETE,{" "}
              {uptime.partial} PARTIAL), {(uptime.share * 100).toFixed(1)} pct of days; {uptime.noReceipt} days with
              no night receipt. A missed night is absent from the record, never filtered out after the fact.
            </p>
            <T head={["date", "scheduled", "games served", "night receipt", "partial reasons"]}
              rows={uptime.table.map((d) => [d.date, d.scheduled ? "yes" : "no", d.served, d.night ?? "none",
                d.reasons.join(", ") || "-"])} />
          </>
        ) : <Reason>{`The uptime receipt ${UPTIME_SRC} could not be read at build time, so the table is not shown.`}</Reason>}
      </Section>

      <Section title="Module self-checks (check_all)" asOf={checks?.asOf} source={CHECK_ALL_SRC}>
        {checks ? (
          <p className="px-3 py-2 text-xs" data-testid="check-all-count">
            {checks.pass} of {checks.total} module self-checks PASS; {checks.noCheck} have no self-check;{" "}
            {checks.other} FAIL/other (check_all_report.json as of {checks.asOf}).
          </p>
        ) : <Reason>{`The check_all report ${CHECK_ALL_SRC} was not present at build time, so no count is shown.`}</Reason>}
      </Section>

      <Section title="Open issues" asOf={issues?.date} source={issues?.file ?? null}>
        {issues ? (
          <p className="px-3 py-2 text-xs" data-testid="open-issues">
            {issues.open} open of {issues.total} issues in the newest daily ledger{" "}
            <a className="font-data underline" href={ghBlob(issues.file)}>{issues.file}</a>.
          </p>
        ) : <Reason>No dated issue ledger under docs/evidence/forward/issues/ was readable at build time.</Reason>}
        {h?.issues ? (
          <p className="px-3 pb-2 text-xs text-muted-foreground">
            In the desk export ({desk?.date}): {h.issues.open} open of {h.issues.total}; open by severity{" "}
            {counts(h.issues.open_by_severity)}; open by kind {counts(h.issues.open_by_kind)}.
          </p>
        ) : null}
      </Section>

      <Section title="Nights and their steps" asOf={desk?.date} source="docs/evidence/forward/nights/">
        {nights.length ? (
          <T head={["night", "status", "reasons", "steps (status / exit / wall s / peak MB)"]}
            rows={[...nights].reverse().map((n) => [n.date, n.status ?? "-", (n.reasons ?? []).join(", ") || "-",
              <ul key="s" className="flex flex-col">
                {n.steps.map((s) => (
                  <li key={s.name}>{s.name}: {s.step_status ?? "-"} / {s.exit_code ?? "-"} / {fmt(s.wall_s, 0)} / {s.peak_mb ?? "-"}
                    {s.reason ? ` (${s.reason})` : ""}</li>
                ))}
              </ul>])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "health")} />}
      </Section>

      <Section title="Desk status (captures, tick, schedule, night)" asOf={desk?.generated_at_utc} source={EXPORT}>
        {h?.desk_status ? (
          <T head={["key", "decision", "reason", "subject", "at (UTC)"]}
            rows={Object.entries(h.desk_status).map(([k, v]) => [k, v.decision ?? "-", v.reason ?? "-",
              v.subject ?? "-", v.ts ?? "-"])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "health.desk_status")} />}
      </Section>

      <Section title="Sources read by this export" asOf={desk?.generated_at_utc} source={EXPORT}>
        {desk ? (
          <T head={["path", "sha256", "mtime UTC"]}
            rows={desk.sources.map((s) => [s.path, (s.sha256 ?? "-").slice(0, 16), s.mtime_utc ?? "-"])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "sources")} />}
      </Section>
    </DeskShell>
  );
}
