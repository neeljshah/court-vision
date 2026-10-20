// /desk/ingame -- HOW IN-GAME WORKS: the live paper-quote pipeline as an
// ordered list, then the day's per-arm counts, refusal reasons and receipt lag
// from the live_shadow fills receipt. Build-time read via desk.server.

import { loadDesk, refusalsFor, fmt } from "@/lib/desk.server";
import { DeskShell, NotAvailable, Section, T } from "@/components/desk/DeskShell";

export const metadata = {
  title: "How in-game works",
  description: "Paper only: state capture, per-sport fit, arms, live paper quote, fill realism, markout.",
};

const STEPS: [string, string][] = [
  ["State capture",
    "Two local recorders append the venue order book (Kalshi) and the game state feed to per-sport, per-UTC-day " +
    "shards. Every row keeps its own receipt time, so later steps only see what was known at that instant."],
  ["Per-sport fit",
    "Once a day, offline, the scoreboard's validated history pair is fit into a frozen calibration per sport " +
    "(nba, nfl, soccer, tennis). MLB has no daily fit; its in-game calibration is read from scoreboard arms B and C " +
    "against the mid. Nothing is refit during a game."],
  ["Arms",
    "Each tick, for each in-window game, every arm turns the freshest book and state into a probability: the " +
    "venue mid itself, the frozen B/C fits, an MLB blend of the frozen pregame mid with the live state, and an " +
    "NBA logistic pricer. Stale books or state, a missing pregame mid, or a final game are counted refusals."],
  ["Live paper quote",
    "An arm that passes its checks writes a hypothetical one-contract maker quote intent per side (yes bid / no " +
    "bid) with an expiry. No order is sent: there is no venue client and no network access on this path."],
  ["Fill realism",
    "After the day closes, each intent is replayed against the captured trade prints. A quote is credited only " +
    "when prints during its life trade through its price, or deplete the modelled queue ahead of it; an unknown " +
    "queue is never treated as depleted."],
  ["Markout",
    "For each credited paper fill, the later mid minus the fill price (fee netted) at fixed horizons, in " +
    "probability points per contract. A markout is a microstructure diagnostic, clustered by game."],
];

export default function DeskIngamePage() {
  const desk = loadDesk();
  const ig = desk?.ingame ?? null;
  const src = ig ? `docs/evidence/forward/live_shadow/${ig.date}.json` : null;

  return (
    <DeskShell desk={desk} title="How in-game works" active="/desk/ingame">
      <Section title="Pipeline (one live paper quote, end to end)">
        <ol className="flex flex-col gap-3 px-3 py-3">
          {STEPS.map(([h, body], i) => (
            <li key={h} className="flex gap-3">
              <span className="font-data text-[12px] text-faint">{i + 1}.</span>
              <div>
                <p className="text-[13px] font-semibold text-foreground">{h}{i < STEPS.length - 1 ? "  ->" : ""}</p>
                <p className="text-[12px] leading-relaxed text-muted-foreground">{body}</p>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="Arms by sport (live recorder)" asOf={ig?.date} source={src}>
        {ig?.sport_arms ? (
          <T head={["sport", "arms"]} rows={Object.entries(ig.sport_arms).map(([s, a]) => [s, a.join(", ")])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "ingame")} />}
      </Section>

      <Section title={`Quote counts by arm${ig ? ` (${ig.date}, receipt ${ig.status ?? "-"})` : ""}`} asOf={ig?.date} source={src}>
        {ig ? (
          <>
            <T head={["arm", "rows", "quote intervals yes / no", "games", "quote hours", "queue unknown",
              "markout 60 s (n)", "markout 300 s (n)", "verdict"]}
              rows={Object.entries(ig.arms).map(([a, v]) => [a, v.n_rows ?? "-",
                v.n_intervals ? `${v.n_intervals.yes ?? "-"} / ${v.n_intervals.no ?? "-"}` : "-",
                v.n_games ?? "-", fmt(v.quote_hours, 2), v.queue_unknown ?? "-",
                v.markout_through["60"] ? `${fmt(v.markout_through["60"].mean_prob_points)} (${v.markout_through["60"].n})` : "-",
                v.markout_through["300"] ? `${fmt(v.markout_through["300"].mean_prob_points)} (${v.markout_through["300"].n})` : "-",
                v.verdict ?? "-"])} />
            <p className="px-3 py-2 text-[12px] text-faint">
              Markouts in probability points per contract (through-fills). Receipt reason: {ig.reason ?? "-"};
              incomplete tickers {ig.incomplete_tickers}; unpaired games {ig.unpaired_games ?? "-"}.
            </p>
          </>
        ) : <NotAvailable refusals={refusalsFor(desk, "ingame")} />}
      </Section>

      <Section title="Refusal reasons" asOf={ig?.date} source={src}>
        {ig ? (
          <T head={["reason", "count"]}
            rows={[...Object.entries(ig.refusals), ...Object.entries(ig.section_refusals)].map(([k, v]) => [k, v])} />
        ) : <NotAvailable refusals={refusalsFor(desk, "ingame")} />}
      </Section>

      <Section title="Receipt lag" asOf={ig?.date} source={src}>
        {ig ? (
          <T head={["n", "p50 s", "p90 s", "max s", "gap s"]}
            rows={[[ig.receipt_lag_s.n ?? "-", fmt(ig.receipt_lag_s.p50, 1),
              ig.receipt_lag_s.p90 == null ? `not available: ${ig.receipt_lag_s.p90_note}` : fmt(ig.receipt_lag_s.p90, 1),
              fmt(ig.receipt_lag_s.max, 1), fmt(ig.gap_s, 1)]]} />
        ) : <NotAvailable refusals={refusalsFor(desk, "ingame")} />}
      </Section>
    </DeskShell>
  );
}
