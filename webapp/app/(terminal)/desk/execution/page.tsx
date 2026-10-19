// /desk/execution -- maker-only paper quoting, quote pacing, fill realism,
// markouts and the latency ledger. Build-time read via desk.server.

import { loadDesk, refusalsFor, fmt } from "@/lib/desk.server";
import { DeskShell, NotAvailable, Section, T } from "@/components/desk/DeskShell";

export const metadata = {
  title: "Desk execution",
  description: "Paper only: maker-only quotes, fill realism, markouts and latency on the recorded tape.",
};

function PaceBar({ hours, max }: { hours: number; max: number }) {
  return (
    <div className="h-1.5 w-40 bg-surface-2">
      <div className="h-full bg-info" style={{ width: `${Math.round((100 * hours) / Math.max(max, 1e-9))}%` }} />
    </div>
  );
}

export default function DeskExecutionPage() {
  const desk = loadDesk();
  const ex = desk?.execution ?? null;
  const fr = ex?.fill_realism;
  const lat = ex?.latency;
  const eq = ex?.exec_quality;
  const arms = Object.entries(desk?.ingame?.arms ?? {});
  const maxH = Math.max(0, ...arms.map(([, a]) => a.quote_hours ?? 0));

  return (
    <DeskShell desk={desk} title="Execution (paper)" active="/desk/execution">
      <Section title="Maker-only quoting">
        <p className="px-3 py-2 text-[12px] leading-relaxed text-muted-foreground">
          The desk only ever rests one-contract maker bids on each side; it never takes liquidity and sends no
          orders. Every fill below is a counterfactual credit from replaying the paper quote against the captured
          trade prints, net of the venue maker fee schedule. These are execution-quality diagnostics, not results.
        </p>
      </Section>

      <Section title="Quote pacing (hours quoted per arm)" asOf={desk?.ingame?.date}
        source={desk?.ingame ? `docs/evidence/forward/live_shadow/${desk.ingame.date}.json` : null}>
        {arms.length ? (
          <T head={["arm", "quote hours", ""]}
            rows={arms.map(([a, v]) => [a, fmt(v.quote_hours, 2),
              v.quote_hours == null ? "-" : <PaceBar key="p" hours={v.quote_hours} max={maxH} />])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "ingame")} />}
      </Section>

      <Section title={`Fill realism${fr ? ` (night ${fr.date})` : ""}`} asOf={fr?.date} source={fr?.source}>
        {fr ? (
          <>
            <T head={["TTL s", "units", "quotes placed", "fills credited"]}
              rows={fr.grid_table.map((g) => [g.ttl_s, g.units, g.quotes_placed ?? "-", g.fills_credited ?? "-"])} />
            <p className="px-3 py-2 font-data text-[11px] text-faint">
              by side {JSON.stringify(fr.by_side)}; by fill basis {JSON.stringify(fr.by_fill_basis)};
              quote-life expiries {fr.quote_life_expiry ?? "-"}
            </p>
          </>
        ) : <NotAvailable refusals={refusalsFor(desk, "execution.fill_realism")} />}
      </Section>

      <Section title="Markouts (fill realism; probability points x 100 per contract, fill-weighted; a diagnostic)" asOf={fr?.date} source={fr?.source}>
        {fr ? (
          <T head={["horizon s", "n", "mean"]}
            rows={Object.entries(fr.markout_cents_by_horizon_s).map(([h, v]) => [h, v.n, fmt(v.mean, 2)])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "execution.fill_realism")} />}
        {refusalsFor(desk, "execution.markouts").length > 0 &&
          <NotAvailable refusals={refusalsFor(desk, "execution.markouts")} />}
      </Section>

      <Section title="Latency ledger (first mid change minus game event, s)" source={lat?.source}>
        {lat ? (
          <T head={["sport", "feed", "games", "n", "p10", "p50", "p90", "p99", "book moved first"]}
            rows={lat.pooled.map((p) => {
              const q: Record<string, number> = p.first_mid_change_minus_event_s ?? {};
              return [p.sport, p.feed, p.games ?? "-", q.n ?? "-", q.p10 ?? "-", q.p50 ?? "-", q.p90 ?? "-",
                q.p99 ?? "-", p.book_moved_first_share == null ? "-" : fmt(p.book_moved_first_share, 3)];
            })} />
        ) : <NotAvailable refusals={refusalsFor(desk, "execution.latency")} />}
      </Section>

      <Section title="Execution-quality receipt" source={eq?.source}>
        {eq ? (
          <div className="px-3 py-2 text-[12px]">
            <p className="font-data text-[11px] text-faint">
              days {(eq.days ?? []).join(", ")}; estimand {eq.estimand_version ?? "-"}; census {JSON.stringify(eq.census)}
            </p>
            <p className="microlabel mt-2">not verified</p>
            <ul className="list-disc pl-5 text-[12px] text-muted-foreground">
              {(eq.not_verified ?? []).map((x) => <li key={x}>{x}</li>)}
            </ul>
          </div>
        ) : <NotAvailable refusals={refusalsFor(desk, "execution.exec_quality")} />}
      </Section>
    </DeskShell>
  );
}
