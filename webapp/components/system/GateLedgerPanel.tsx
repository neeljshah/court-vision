"use client";

import { useCallback, useMemo, useState } from "react";
import { Panel, Unavailable, Badge } from "@/components/p6/Primitives";
import { cn } from "@/lib/utils";
import { useLiveData } from "@/lib/useLiveData";
import {
  InfoTip,
  Legend,
  SignalVerdictBadge,
  type SignalVerdict,
} from "@/components/depth";
import {
  systemApi,
  type FunnelArtifacts,
  type RichLedgerRow,
} from "./systemApi";

// GateLedgerPanel -- the GATE-VERDICT LEDGER as a rich, sortable table. Every
// signal the leak-free gate ran is one row: sport | signal/layer | verdict |
// deciding stat | corpora | base | vs_close. Read straight from the on-disk
// artifacts (data/frontend/funnel/*.json) via the page-local Next route, so the
// full ledger renders even when the Python service is down.
//
// HONESTY: every verdict is CALIBRATION-only; vs_close is UNPROVEN everywhere.
// A REJECT is a SUCCESS (markets are efficient). The lone SHIP (soccer corners)
// is a calibration survivor, NOT a market edge. There is NO $/ROI/payout field.

const SPORT_ORDER = ["soccer", "soccer_intl", "nba", "mlb", "tennis", "platform"];
// Canonical verdicts SignalVerdictBadge renders; others get an inline chip.
const CANON: SignalVerdict[] = ["SHIP", "REJECT", "INSUFFICIENT_DATA", "TIER3_BLOCKED"];

type SortKey = "verdict" | "sport" | "layer" | "corpora";

function verdictRank(v: string): number {
  // SHIP first (the survivor), then COHERENCE, PARTIAL, REJECT, then blocked/insufficient.
  const order = ["SHIP", "PROMOTE", "COHERENCE", "PARTIAL", "REJECT", "TIER3_BLOCKED", "INSUFFICIENT_DATA"];
  const i = order.indexOf(v);
  return i < 0 ? order.length : i;
}

function VerdictCell({ row }: { row: RichLedgerRow }) {
  if (CANON.includes(row.verdict as SignalVerdict)) {
    return (
      <SignalVerdictBadge
        verdict={row.verdict as SignalVerdict}
        stat={row.deciding_stat}
      />
    );
  }
  // PARTIAL / COHERENCE -- inline chip + InfoTip (not one of the 4 canon verdicts).
  const tone =
    row.verdict === "COHERENCE"
      ? "border-success/50 bg-success/10 text-success"
      : "border-warning/50 bg-warning/10 text-warning";
  const note =
    row.verdict === "COHERENCE"
      ? "coherent re-exposure off one engine matrix -- same calibration, no edge"
      : "replicated in ONE direction only -- not promoted; kept as scouting";
  return (
    <span className="inline-flex items-center gap-1">
      <span
        className={cn(
          "inline-flex rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase",
          tone,
        )}
        title={`${row.deciding_stat} -- ${note}`}
      >
        {row.verdict}
      </span>
      <InfoTip text={`${row.deciding_stat} -- ${note}`} ariaLabel="what does this verdict mean?" />
    </span>
  );
}

function HeaderCell({
  label,
  sortKey,
  active,
  dir,
  onSort,
  tip,
}: {
  label: string;
  sortKey?: SortKey;
  active?: boolean;
  dir?: 1 | -1;
  onSort?: (k: SortKey) => void;
  tip?: string;
}) {
  // aria-sort reflects the live sort state for screen readers: ascending /
  // descending on the active column, "none" on the other sortable columns.
  const ariaSort: React.AriaAttributes["aria-sort"] = sortKey
    ? active
      ? dir === 1
        ? "ascending"
        : "descending"
      : "none"
    : undefined;
  return (
    <th className="pb-2 pr-3 font-medium" scope="col" aria-sort={ariaSort}>
      <span className="inline-flex items-center gap-1">
        {sortKey ? (
          <button
            type="button"
            onClick={() => onSort?.(sortKey)}
            aria-label={`Sort by ${label}${
              active ? (dir === 1 ? ", ascending" : ", descending") : ""
            }`}
            className={cn(
              "rounded-sm uppercase tracking-wide hover:text-foreground",
              "focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active ? "text-foreground" : "",
            )}
          >
            {label}
            {active ? <span aria-hidden>{dir === 1 ? " v" : " ^"}</span> : null}
          </button>
        ) : (
          <span className="uppercase tracking-wide">{label}</span>
        )}
        {tip ? <InfoTip text={tip} ariaLabel={`what is ${label}?`} /> : null}
      </span>
    </th>
  );
}

export function GateLedgerPanel() {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "verdict", dir: 1 });

  // Poll the funnel-artifacts ledger (was one-shot). useLiveData retains
  // last-good rows and backs off on failure; the gate ledger refreshes slowly.
  const fetcher = useCallback(
    (signal: AbortSignal) => systemApi.artifacts(signal),
    [],
  );
  const { data, error: err } = useLiveData<FunnelArtifacts>(fetcher, {
    intervalMs: 120_000,
    staleAfterSec: 30 * 60,
  });

  // Wrap in its own useMemo so the array identity is stable across renders
  // (a bare `?? []` makes a fresh [] every render and churns the sorted memo).
  const rows = useMemo(() => data?.ledger?.rows ?? [], [data]);
  const counts = data?.ledger?.counts ?? {};
  const nShip = (counts["SHIP"] || 0) + (counts["PROMOTE"] || 0);

  const sorted = useMemo(() => {
    const cmp = (a: RichLedgerRow, b: RichLedgerRow): number => {
      let r = 0;
      if (sort.key === "verdict") r = verdictRank(a.verdict) - verdictRank(b.verdict);
      else if (sort.key === "sport")
        r = SPORT_ORDER.indexOf(a.sport) - SPORT_ORDER.indexOf(b.sport);
      else if (sort.key === "corpora") r = (a.corpora || 0) - (b.corpora || 0);
      else r = a.layer.localeCompare(b.layer);
      if (r === 0) r = a.layer.localeCompare(b.layer);
      return r * sort.dir;
    };
    return [...rows].sort(cmp);
  }, [rows, sort]);

  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: 1 }));

  return (
    <Panel
      title="gate-verdict ledger (every signal tested, leak-free)"
      right={
        data ? (
          <span className="flex items-center gap-1.5">
            <Badge tone="green">{nShip} ship</Badge>
            <Badge tone="amber">{rows.length - nShip} reject / other</Badge>
          </span>
        ) : null
      }
    >
      {err ? (
        <Unavailable reason={err} />
      ) : !data ? (
        <p className="text-sm text-muted-foreground">loading...</p>
      ) : rows.length === 0 ? (
        <Unavailable reason="no gate verdicts recorded on disk yet" />
      ) : (
        <>
          <Legend
            title="what each verdict means"
            className="mb-3"
            items={[
              { label: "SHIP", swatch: "bg-success", tip: "passed both-direction cross-corpus on CALIBRATION (held-out Brier) -- vs_close still UNPROVEN, not an edge" },
              { label: "PARTIAL", swatch: "bg-warning", tip: "replicated in ONE direction only; not promoted, kept as scouting" },
              { label: "REJECT", swatch: "bg-muted", tip: "a SUCCESS: the market already prices this; recorded, never force-fed" },
              { label: "TIER3_BLOCKED", swatch: "bg-warning", tip: "data could not be acquired; durable dead-end record" },
              { label: "deciding stat", term: "brier" },
              { label: "corpora", tip: "number of independent corpora the gate replicated across (>=2 required; single-fold lifts are artifacts)" },
              { label: "vs_close", term: "vs_close" },
            ]}
          />
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
                  <HeaderCell label="Sport" sortKey="sport" active={sort.key === "sport"} dir={sort.dir} onSort={onSort} />
                  <HeaderCell label="Signal / layer" sortKey="layer" active={sort.key === "layer"} dir={sort.dir} onSort={onSort} />
                  <HeaderCell label="Verdict" sortKey="verdict" active={sort.key === "verdict"} dir={sort.dir} onSort={onSort} />
                  <HeaderCell label="Deciding stat" tip="The leak-free clustered-DM p-value / held-out Brier delta that decided the verdict." />
                  <HeaderCell label="Corpora" sortKey="corpora" active={sort.key === "corpora"} dir={sort.dir} onSort={onSort} tip="independent corpora replicated across" />
                  <HeaderCell label="vs close" tip="UNPROVEN everywhere: no liquid in-play closing price exists to grade against." />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {sorted.map((r) => (
                  <tr key={r.id} className="align-top text-foreground">
                    <td className="py-2 pr-3 font-mono text-[10px] uppercase text-muted-foreground">{r.sport}</td>
                    <td className="py-2 pr-3 font-mono text-[11px] text-foreground">
                      {r.layer}
                      {r.base ? (
                        <div className="mt-0.5 max-w-[22rem] truncate font-mono text-[9px] text-faint" title={`base / champion: ${r.base}`}>
                          base: {r.base}
                        </div>
                      ) : null}
                    </td>
                    <td className="py-2 pr-3"><VerdictCell row={r} /></td>
                    <td className="py-2 pr-3 font-mono text-[10px] text-muted-foreground" title={r.deciding_stat}>
                      <span className="block max-w-[16rem] truncate">{r.deciding_stat}</span>
                    </td>
                    <td className="py-2 pr-3 font-mono text-[11px] text-muted-foreground">{r.corpora || "--"}</td>
                    <td className="py-2 font-mono text-[10px] text-amber-600/80">
                      {r.vs_close.startsWith("UNPROVEN") ? "UNPROVEN" : r.vs_close}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-faint">
            {data.honest_note}
          </p>
        </>
      )}
    </Panel>
  );
}
