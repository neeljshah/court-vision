// /desk/health -- paper nights and their steps, the desk status (captures,
// tick, schedule, night), and the open issue counts. Build-time read.

import { loadDesk, refusalsFor, fmt } from "@/lib/desk.server";
import { DeskShell, NotAvailable, Section, T } from "@/components/desk/DeskShell";

export const metadata = {
  title: "Desk health",
  description: "Paper only: nightly runs, steps, desk status and issues.",
};

export default function DeskHealthPage() {
  const desk = loadDesk();
  const h = desk?.health ?? null;
  const nights = h?.nights ?? [];

  return (
    <DeskShell desk={desk} title="Desk health" active="/desk/health">
      <Section title="Nights" asOf={desk?.date} source="docs/evidence/forward/nights/">
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

      <Section title="Desk status (captures, tick, schedule, night)" source="data/cache/paper_desk/status.json">
        {h?.desk_status ? (
          <T head={["key", "decision", "reason", "subject", "ts"]}
            rows={Object.entries(h.desk_status).map(([k, v]) => [k, v.decision ?? "-", v.reason ?? "-",
              v.subject ?? "-", v.ts ?? "-"])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "health.desk_status")} />}
      </Section>

      <Section title="Issues" source="data/cache/paper_desk/issues/state.json">
        {h?.issues ? (
          <div className="px-3 py-2 font-data text-[12px]">
            <p>total {h.issues.total}; open {h.issues.open}</p>
            <p className="text-faint">by status {JSON.stringify(h.issues.by_status)}</p>
            <p className="text-faint">open by severity {JSON.stringify(h.issues.open_by_severity)}</p>
            <p className="text-faint">open by kind {JSON.stringify(h.issues.open_by_kind)}</p>
          </div>
        ) : <NotAvailable refusals={refusalsFor(desk, "health.issues")} />}
      </Section>

      <Section title="Sources read by this export">
        {desk ? (
          <T head={["path", "sha256", "mtime UTC"]}
            rows={desk.sources.map((s) => [s.path, (s.sha256 ?? "-").slice(0, 16), s.mtime_utc ?? "-"])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "sources")} />}
      </Section>
    </DeskShell>
  );
}
