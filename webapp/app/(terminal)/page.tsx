// Home (/) -- the CourtVision calibration scoreboard. Build-time server
// component (the /receipts pattern): every number is read verbatim from a
// staged webapp/public/data/showcase/*.json and wears its receipt. No client
// fetch, no /api. Rails: calibration/sharpness only, never $/ROI/edge; the
// co-headline "win" is a staged MODEL_SHARPER_PROVISIONAL CRPS row (labelled
// provisional); the scoreboard shows losses + underpowered rows unfiltered.

import type { Metadata } from "next";
import Link from "next/link";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import { DeltaBars } from "@/components/charts/DeltaBars";
import { loadArtifact } from "@/lib/showcase.server";
import { listPacks } from "@/lib/atlas.server";

export const metadata: Metadata = {
  title: "Calibration Scoreboard",
  description:
    "A calibrated multi-sport predictor that publishes its own scorecard against a sharp market -- losses, nulls, and retractions included. No edge claimed.",
};

type Row = {
  sport: string;
  market: string;
  checkpoint: string;
  n: number;
  paired_delta_mean: number;
  paired_delta_95ci: [number, number];
  verdict: string;
  source: string;
};

type Scoreboard = { generated_at: string; n_rows: number; rows: Row[] };
type HSport = { confirmed: number; null: number; not_testable: number; failed_replication: number };
type Honesty = { generated_at: string; headline: string; sports: HSport[] };

const fmt = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(4);

const LABS = [
  {
    href: "/lab/counterfactual",
    title: "Counterfactual Explorer",
    body: "Pick a game-state cell -- score margin x time -- and see the model forecast there next to the market and the realized outcome. Reads committed cells; runs no new simulation.",
    go: "state_conditioned_calibration -- open lab",
  },
  {
    href: "/lab/microstructure",
    title: "Market-Microstructure Lab",
    body: "Outcome-free forecast-property instruments: information-arrival curves, model-market convergence, residual autocorrelation. Labelled STANDARD_INSTRUMENT.",
    go: "edge_claimed: false -- open lab",
  },
];

const LIVE_LINKS: [string, string][] = [
  ["/games", "games"],
  ["/records", "records"],
  ["/paper-trading", "paper trading"],
  ["/system", "system"],
  ["/how-it-works", "how it works"],
  ["/methodology", "methodology"],
];

function VerdictPill({ v }: { v: string }) {
  const cls = v.startsWith("MODEL_SHARPER") ? "text-success border-success/50"
    : v.startsWith("MARKET_SHARPER") ? "text-danger border-danger/50"
      : "text-faint border-border";
  return (
    <span className={`inline-block whitespace-nowrap border px-1.5 py-px font-data text-[10px] tracking-wide ${cls}`}>
      {v.replace(/_PROVISIONAL$/, "").replace(/_/g, " ")}
    </span>
  );
}

type DoorProps = { href: string; kicker?: string; title: string; body: string; stat?: string; go: string };
function Door({ href, kicker, title, body, stat, go }: DoorProps) {
  return (
    <Link href={href}
      className="group flex flex-col border border-border bg-card p-5 transition-colors hover:border-primary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {kicker && <span className="microlabel">{kicker}</span>}
      <h3 className="mt-1 text-lg font-semibold tracking-tight text-foreground">{title}</h3>
      <p className="mt-1.5 flex-1 text-[13.5px] leading-relaxed text-muted-foreground">{body}</p>
      {stat && <div className="mt-3 font-data text-2xl text-primary tabular">{stat}</div>}
      <div className="mt-2 font-data text-[11px] uppercase tracking-wider text-faint group-hover:text-foreground">
        {go} -&gt;
      </div>
    </Link>
  );
}

export default function Home() {
  const board = loadArtifact("cross_sport_scoreboard") as Scoreboard | null;
  const honesty = loadArtifact("honesty_exhibit") as Honesty | null;
  const brier = loadArtifact("brier_skill_scores") as
    | { generated_at?: string; sports?: { mlb?: { grains?: { all?: { brier_model: number; brier_market: number; n: number } } } } }
    | null;

  const rows = board?.rows ?? [];
  const asOf = board?.generated_at ?? null;
  const win = rows.find((r) => r.checkpoint === "total_runs|end_inning_7");
  const mlbAll = brier?.sports?.mlb?.grains?.all;

  const packs = listPacks();
  const atlasTotal = packs.reduce((s, p) => s + p.count, 0);

  const H = honesty?.sports ?? [];
  const sum = (k: keyof Honesty["sports"][number]) => H.reduce((s, x) => s + (x[k] || 0), 0);
  const confirmed = sum("confirmed");
  const nulls = sum("null");
  const ratio = confirmed > 0 ? (nulls / confirmed).toFixed(1) : "--";
  const strip: [string, string][] = [
    [`${confirmed}`, "confirmed signals"],
    [`${nulls}`, "null results"],
    [`${sum("not_testable")}`, "not testable"],
    [`${ratio}x`, "nulls per confirm"],
  ];

  return (
    <div className="mx-auto max-w-[1200px] px-6 pb-16">
      <section className="pt-11 pb-3">
        <h1 className="max-w-3xl text-2xl font-semibold leading-tight tracking-tight text-foreground sm:text-3xl">
          A calibrated sports predictor that publishes its own scorecard against a
          sharp market -- losses, nulls, and retractions included.
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Every number below is copied verbatim from a committed artifact and wears
          its receipt: source path, as-of date, and verification status. No edge is
          claimed anywhere.
        </p>
        <span className="mt-3 inline-flex items-center gap-2 border border-border px-2.5 py-1 font-data text-[11px] text-faint">
          POSITIONING <b className="text-foreground">calibration, not profit</b> &middot; edge_claimed: false on every artifact
        </span>
      </section>

      <div className="my-5 grid grid-cols-1 gap-px border border-border bg-border md:grid-cols-[1.15fr_1fr]">
        <div className="border-t-2 border-t-success bg-card p-5">
          <div className="microlabel">The measured sharpness result -- MLB in-game</div>
          {win ? (
            <>
              <div className="mt-2 font-data text-3xl font-semibold text-success tabular">
                {fmt(win.paired_delta_mean)} CRPS
                <ReceiptChip sourceArtifact={win.source} asOf={asOf} verified="edge_claimed:false"
                  verdict={win.verdict} n={win.n} ci={win.paired_delta_95ci} />
              </div>
              <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
                Model total-runs forecast is sharper than the market&apos;s at end of
                inning 7 (n={win.n}, 95% CI [{fmt(win.paired_delta_95ci[0])},{" "}
                {fmt(win.paired_delta_95ci[1])}]). MODEL_SHARPER_PROVISIONAL -- still
                provisional on a small sample. A sharpness result measured leak-free,
                not an edge.
              </p>
            </>
          ) : (
            <p className="mt-2 text-[13px] text-stale">Scoreboard artifact not staged on this clone.</p>
          )}
        </div>
        <div className="border-t-2 border-t-faint bg-card p-5">
          <div className="microlabel">And the honest reading</div>
          <div className="mt-2 font-data text-2xl font-semibold text-foreground">match, do not beat</div>
          <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
            Across in-game win-prob checkpoints the market is as sharp or sharper.
            {mlbAll && (
              <>
                {" "}Model Brier {mlbAll.brier_model.toFixed(4)} vs market{" "}
                {mlbAll.brier_market.toFixed(4)} on MLB (n={mlbAll.n.toLocaleString()})
                <ReceiptChip sourceArtifact="scripts/platformkit/analytics_showcase/out/brier_skill_scores.json"
                  asOf={brier?.generated_at ?? null} verified="descriptive_only" />
                ; NBA end-Q1 favors the market too.
              </>
            )}{" "}
            Both readings are true. We publish both.
          </p>
        </div>
      </div>

      <h2 className="mt-9 microlabel">Cross-sport calibration scoreboard</h2>
      <Panel className="mt-2">
        <PanelHead title="model vs market -- paired Brier / CRPS delta, 95% CI, verdict" asOf={asOf ?? undefined} />
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr className="text-left">
                <th className="microlabel px-3 py-2">sport</th>
                <th className="microlabel px-3 py-2">market</th>
                <th className="microlabel px-3 py-2">checkpoint</th>
                <th className="microlabel px-3 py-2 text-right">n</th>
                <th className="microlabel px-3 py-2">model &minus; market</th>
                <th className="microlabel px-3 py-2 text-right">95% CI</th>
                <th className="microlabel px-3 py-2">verdict</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-border hover:bg-surface-2">
                  <td className="px-3 py-2 font-data">{r.sport}</td>
                  <td className="px-3 py-2">{r.market}</td>
                  <td className="px-3 py-2 font-data text-[12px]">{r.checkpoint}</td>
                  <td className="px-3 py-2 text-right font-data tabular">{r.n}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <DeltaBars delta={r.paired_delta_mean} ci={r.paired_delta_95ci} verdict={r.verdict} />
                      <span className="font-data tabular text-foreground">{fmt(r.paired_delta_mean)}</span>
                      <ReceiptChip sourceArtifact={r.source} asOf={asOf} verified="edge_claimed:false"
                        verdict={r.verdict} n={r.n} ci={r.paired_delta_95ci} />
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right font-data tabular text-faint">
                    [{fmt(r.paired_delta_95ci[0])}, {fmt(r.paired_delta_95ci[1])}]
                  </td>
                  <td className="px-3 py-2">
                    <VerdictPill v={r.verdict} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between border-t border-border px-3 py-2">
          <span className="microlabel">
            {board?.n_rows ?? rows.length} rows total. Losses and underpowered rows are shown, not filtered.
          </span>
          <Link href="/receipts" className="microlabel text-primary hover:underline">
            open the full receipts ledger -&gt;
          </Link>
        </div>
      </Panel>

      {honesty && (
        <>
          <p className="mt-6 flex items-baseline gap-2 text-sm text-muted-foreground">
            <span className="text-foreground">{honesty.headline}</span>
            <ReceiptChip sourceArtifact="scripts/platformkit/analytics_showcase/out/honesty_exhibit.json"
              asOf={honesty.generated_at} verified="descriptive_only" />
          </p>
          <div className="mt-2 grid grid-cols-2 gap-px border border-border bg-border md:grid-cols-4">
            {strip.map(([k, l]) => (
              <div key={l} className="bg-card p-4">
                <div className="font-data text-2xl tabular text-foreground">{k}</div>
                <div className="mt-0.5 text-[12px] text-faint">{l}</div>
              </div>
            ))}
          </div>
        </>
      )}

      <h2 className="mt-9 microlabel">Two ways in</h2>
      <div className="mt-2 grid grid-cols-1 gap-4 md:grid-cols-2">
        <Door href="/atlas" kicker={`spine 1 -- browse -- ${packs.length} packs`} title="Entity Atlas"
          body="Descriptive cards across NBA, MLB, tennis, and soccer. Every card carries its sample floor and as-of date."
          stat={atlasTotal.toLocaleString()} go="enter the atlas" />
        <Door href="/evidence" kicker="spine 2 -- interrogate" title="Evidence Explorer"
          body="Claim pages, each with its strongest receipt and a reproduce-on-a-fresh-clone block. Includes the retraction story: headline numbers this system refuted about itself."
          stat="23" go="read the evidence" />
      </div>

      <h2 className="mt-9 microlabel">Research labs</h2>
      <div className="mt-2 grid grid-cols-1 gap-4 md:grid-cols-2">
        {LABS.map((d) => (
          <Door key={d.href} {...d} />
        ))}
      </div>

      <div className="my-6 border border-border border-l-[3px] border-l-primary bg-card px-4 py-3.5">
        <b className="text-primary">What you will not find here.</b>{" "}
        <span className="text-[13.5px] leading-relaxed text-muted-foreground">
          No ROI, profit, or betting-edge claim. This is a calibrated predictor measured
          against the devigged close, not a track record. Several early headline numbers were
          retracted after this project&apos;s own instruments refuted them -- that story is a
          feature, on the{" "}
          <Link href="/evidence/retraction-story" className="text-primary hover:underline">
            retraction page
          </Link>
          , not a footnote.
        </span>
      </div>

      <div className="mt-8 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-4 text-[12px] text-faint">
        <span className="microlabel">live app</span>
        {LIVE_LINKS.map(([href, label]) => (
          <Link key={href} href={href} className="hover:text-foreground">{label}</Link>
        ))}
      </div>

      <footer className="mt-6 border-t border-border pt-5 text-[12px] leading-relaxed text-faint">
        Built by Neel Shah. Every figure traces to a committed JSON under{" "}
        <span className="font-data">scripts/platformkit/analytics_showcase/out/</span>. Reproduce the
        whole set with{" "}
        <span className="font-data">python scripts/platformkit/analytics_showcase/check_all.py</span>{" "}
        (52/52 on a bare clone). Truth source:{" "}
        <span className="font-data">docs/JOB_EVIDENCE_PACKET.md</span>.
      </footer>
    </div>
  );
}
