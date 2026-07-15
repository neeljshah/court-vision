"use client";

import type { Report } from "@/lib/p5api";
import { Panel, Unavailable, Badge, timeAgoIso } from "./Primitives";
import { fmtPct } from "@/lib/utils";

// STALE_MS -- a live feed older than this (by its own as_of) reads stale->RED.
const STALE_MS = 15 * 60_000;

// liveFreshness -- derive an ACTUAL freshness signal from the live feed's as_of
// data age, NEVER from a game-state string (LL-P0-03: "Q3 7:42" is a state, not a
// freshness status).
// "absent"  -- as_of is null/missing/unparseable: a missing-data state, NEUTRAL
// "stale"   -- as_of is a valid but old timestamp: RED (stale-never-green)
// "fresh"   -- as_of is a valid recent timestamp: GREEN
function liveFreshness(asOf: string | null | undefined): "fresh" | "stale" | "absent" {
  if (!asOf) return "absent";
  const t = Date.parse(asOf);
  if (Number.isNaN(t)) return "absent";
  return Date.now() - t < STALE_MS ? "fresh" : "stale";
}

// LiveFreshnessPill -- absent -> neutral slate (missing data, not an error);
// stale -> RED (stale-never-green rail, old timestamp is genuine staleness);
// fresh -> green (genuinely recent feed).
function LiveFreshnessPill({ asOf }: { asOf: string | null | undefined }) {
  const status = liveFreshness(asOf);
  if (status === "fresh") {
    return <Badge tone="green">{`fresh ${timeAgoIso(asOf as string)}`}</Badge>;
  }
  if (status === "stale") {
    return <Badge tone="red">{`STALE ${timeAgoIso(asOf as string)}`}</Badge>;
  }
  // absent: missing-data state, neutral (never red for a mere absent timestamp)
  return <Badge tone="slate">no live feed</Badge>;
}

// GameReport -- pregame model probs + live in-game state + market rows, all
// straight from /api/report. Freshness/provenance badges from meta.as_of and
// market book/captured_at. Degrades to unavailable per-section, never fabricated.
export function GameReport({ report }: { report: Report | null }) {
  if (!report || report.status === "unavailable") {
    return (
      <Panel title="Game report">
        <Unavailable reason={report?.reason || "no report for this game"} />
      </Panel>
    );
  }
  const pg = report.pregame;
  const live = report.live;
  const meta = report.meta;

  return (
    <Panel
      title="Game report (pregame + in-game)"
      right={
        // Header freshness is RE-DERIVED client-side from meta.as_of DATA AGE
        // (liveFreshness), NEVER trusted from the server-supplied
        // meta.freshness.status -- a 'fresh'/null status on an hours-old as_of
        // must still read STALE/RED (stale-never-green rail). Mirrors the
        // LiveLinesPanel/freshnessStatus + LiveFreshnessPill derivation below.
        <span className="inline-flex items-center gap-1.5">
          <LiveFreshnessPill asOf={meta?.as_of} />
          <span className="font-mono text-[10px] text-muted-foreground">{report.sport}</span>
        </span>
      }
    >
      {/* Pregame */}
      <div className="mb-4">
        <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
          Pregame
        </div>
        {pg ? (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-medium text-foreground">
              {pg.away} @ {pg.home}
            </span>
            {pg.model_probs ? (
              <span className="font-mono text-xs text-muted-foreground">
                {Object.entries(pg.model_probs)
                  .map(([k, v]) => `${k} ${fmtPct(v, false)}`)
                  .join(" | ")}
              </span>
            ) : null}
            {pg.leak_guard ? (
              <Badge tone={pg.leak_guard.in_sample ? "red" : "green"}>
                {pg.leak_guard.in_sample ? "in-sample" : "leak-free"}
              </Badge>
            ) : null}
          </div>
        ) : (
          <Unavailable reason="no pregame prediction" />
        )}
      </div>

      {/* In-game */}
      <div className="mb-4">
        <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
          In-game (live)
        </div>
        {live && live.status !== "unavailable" ? (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="font-mono text-foreground">
              {live.away_abbr ?? "AWAY"} {live.away_score ?? "--"} |{" "}
              {live.home_abbr ?? "HOME"} {live.home_score ?? "--"}
            </span>
            <Badge tone="slate">
              {live.detail || live.state || "live"}
              {live.period ? ` Q${live.period}` : ""}
              {live.clock ? ` ${live.clock}` : ""}
            </Badge>
            {/* LL-P0-03: freshness from as_of data age, not the game-state string. */}
            <LiveFreshnessPill asOf={live.as_of} />
          </div>
        ) : (
          <Unavailable reason={live?.reason || "no live state"} />
        )}
      </div>

      {/* Markets */}
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
          Markets ({report.markets?.length ?? 0})
        </div>
        {report.markets && report.markets.length ? (
          <table className="w-full text-xs">
            <tbody className="divide-y divide-slate-800">
              {report.markets.map((m, i) => (
                <tr key={i} className="text-foreground">
                  <td className="py-1.5 font-mono">
                    {m.market_type} {m.side}
                    {m.line != null ? ` ${m.line}` : ""}
                  </td>
                  <td className="py-1.5 text-right font-mono tabular-nums">
                    {m.odds.toFixed(2)}
                  </td>
                  <td className="py-1.5 text-right font-mono text-muted-foreground">
                    {fmtPct(m.devigged_prob, false)} devig
                  </td>
                  <td className="py-1.5 text-right font-mono text-[10px] text-faint">
                    {m.book}
                    {m.clv_is_proxy ? " | proxy" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Unavailable reason="no market rows" />
        )}
      </div>
    </Panel>
  );
}
