// HomeVerdictRows -- the home first screen's headline verdicts (DESIGN_PRINCIPLES P2.1 item 2).
// Every block carries verdict word, n, interval, as-of and a receipt chip (P2.4); rows come
// from CANONICAL_FIGURES.json via lib/canonicalFigures.server, largest n first (P2.3).
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import { VerdictLabel, type PacketVerdict } from "@/components/evidence";
import type { CanonicalFigure } from "@/lib/canonicalFigures.server";

const f4 = (v: number) => (v >= 0 ? "+" : "") + v.toFixed(4);
const SPORT: Record<string, string> = { mlb: "MLB", nba: "NBA", soccer: "Soccer" };

/** Packet qualifier: NBA moneyline matches the close only because it is underpowered. */
function qualifier(f: CanonicalFigure): PacketVerdict | null {
  if (f.verdict !== "MATCHES_CLOSE" || f.mde == null || f.ci95 == null) return null;
  return f.ci95[1] - f.ci95[0] > f.mde ? "UNDERPOWERED" : null;
}

export function HomeVerdictRows({ figures }: { figures: CanonicalFigure[] }) {
  if (!figures.length) {
    return <p className="text-sm text-stale">docs/evidence/CANONICAL_FIGURES.json not staged on this clone.</p>;
  }
  return (
    <ul className="m-0 grid list-none gap-px border border-border bg-border p-0 md:grid-cols-3" aria-label="Pregame against the devigged close">
      {figures.map((f) => {
        const q = qualifier(f);
        return (
          <li key={f.key} className="metric bg-card p-3" data-key={f.key}>
            <div className="text-xs text-muted-foreground">
              {SPORT[f.sport] ?? f.sport} {f.market}, pregame vs devigged close
            </div>
            <div className="mt-1 flex flex-wrap items-baseline gap-x-2">
              {/* VerdictLabel throws on a non-packet word, so a stray artifact verdict fails the build. */}
              <span data-role="verdict"><VerdictLabel verdict={f.verdict as PacketVerdict} qualifier={false} /></span>
              {q && <span data-role="qualifier"><VerdictLabel verdict={q} qualifier={false} /></span>}
            </div>
            <div className="mt-1 font-data text-sm tabular text-foreground">
              Brier {(f.model?.toFixed(4) ?? "--")} model vs {(f.close?.toFixed(4) ?? "--")} close
              <span className="text-muted-foreground"> (lower is better)</span>
            </div>
            <div className="font-data text-xs tabular text-muted-foreground">
              gap <span data-role="gap">{f.gap != null ? f4(f.gap) : "--"}</span>{" "}
              <span data-role="interval">
                {f.ci95 ? `95% CI [${f4(f.ci95[0])}, ${f4(f.ci95[1])}]` : "no interval"}
              </span>
            </div>
            <div className="font-data text-xs text-muted-foreground">
              <span data-role="n">n = {f.n?.toLocaleString("en-US") ?? "--"} games</span> &middot;{" "}
              <span data-role="asof">as of {f.as_of}</span>
              <span data-role="receipt">
                <ReceiptChip sourceArtifact={f.source} asOf={f.as_of} verified="edge_claimed:false"
                  verdict={f.verdict} n={f.n ?? null} ci={f.ci95 ?? null} />
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
