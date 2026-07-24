// JoinedFindings -- renders entity_joins.json items on an entity card: measured
// figures joined in from other already-committed analytics modules, not new
// computation. Server component, no client JS: every item is static per build,
// same as the rest of the entity page. Supporting evidence, so it renders BELOW
// the Scout note / "what stands out" / reading note, never above them.
import { Receipt } from "./Receipt";
import type { JoinItem } from "@/lib/analytics/showcaseData";

export interface JoinedFindingsProps {
  pack: string;
  items: JoinItem[];
  coverage: Record<string, number>;
}

// The coverage sentence must be computed from the pack's own coverage object,
// never hardcoded -- both the numbers and their meaning differ per pack (team
// joins are uniform 30/30; player joins vary per join type).
// A missing/!malformed coverage object must render NO sentence rather than a
// confident "All 0 team cards" -- a wrong coverage claim is worse than none.
function coverageLine(pack: string, coverage: Record<string, number>): string | null {
  const n = coverage.n_in_pack;
  if (!n) return null;
  if (pack === "nba_teams") {
    const joinCount = Object.keys(coverage).filter((k) => k !== "n_in_pack").length;
    return `All ${n} team cards carry these ${joinCount} joins.`;
  }
  if (pack === "nba_players") {
    const withWithout = coverage.with_without ?? 0;
    return `Joined onto ${withWithout} of ${n} player cards; the leaderboard badges cover far fewer.`;
  }
  return `Joined onto ${n} cards in this pack.`;
}

export function JoinedFindings({ pack, items, coverage }: JoinedFindingsProps) {
  if (!items.length) return null;
  const line = coverageLine(pack, coverage);
  return (
    <section style={{ marginTop: 28 }}>
      <h2 className="serif" style={{ fontWeight: 500, fontSize: 20, marginBottom: 6 }}>
        Also measured elsewhere
      </h2>
      {line ? (
        <p style={{ margin: "0 0 14px", fontSize: 13, color: "var(--ink-3)" }}>{line}</p>
      ) : null}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {items.map((item) => (
          <div
            key={item.key}
            style={{ background: "var(--paper-tint)", border: "1px solid var(--rule)", borderRadius: 10, padding: "14px 16px" }}
          >
            <div style={{ fontSize: 12, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".05em", fontWeight: 600 }}>
              {item.label}
            </div>
            <div style={{ fontWeight: 600, fontSize: "1.05rem", lineHeight: 1.3, margin: "8px 0 6px", color: "var(--ink)" }}>
              {item.value}
            </div>
            {item.detail ? (
              <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginBottom: 8 }}>{item.detail}</div>
            ) : null}
            {/* The confound is the whole point of this section: always visible, never
                behind a hover, and never truncated. */}
            <div style={{ fontSize: 12.5, color: "var(--ink-3)", lineHeight: 1.5, marginBottom: 8 }}>
              {item.confound}
            </div>
            <Receipt sourceArtifact={item.source_artifact} verdict="descriptive_only" label="descriptive_only" value={item.value} />
          </div>
        ))}
      </div>
    </section>
  );
}

export default JoinedFindings;
