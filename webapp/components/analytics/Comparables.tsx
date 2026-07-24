// Comparables -- "Most similar in this pack" sidebar box on an entity card.
// Server component, no client JS: nearest neighbours are precomputed at build
// time (entity_comparables.json), same as the rest of the entity page. Only 4
// of 7 packs are covered (nba_players, nba_teams, mlb_batters, soccer); the
// caller renders this box only when the entity has an entry.
import Link from "next/link";
import { Receipt } from "./Receipt";
import type { ComparableItem } from "@/lib/analytics/showcaseData";

export interface ComparablesProps {
  pack: string;
  fieldsUsed: string[];
  similar: ComparableItem[];
  antipode: ComparableItem;
}

function humanize(field: string): string {
  return field.replace(/_/g, " ");
}

export function Comparables({ pack, fieldsUsed, similar, antipode }: ComparablesProps) {
  if (!similar.length) return null;
  const fieldsList = fieldsUsed.map(humanize).join(", ");
  return (
    <div style={{ background: "var(--paper-raised)", border: "1px solid var(--rule)", borderRadius: 10, padding: 18, boxShadow: "var(--shadow-card)", marginBottom: 20 }}>
      <h3 className="serif" style={{ fontWeight: 500, fontSize: 20, marginBottom: 10 }}>Most similar in this pack</h3>
      {similar.slice(0, 5).map((item) => (
        <Link
          key={item.slug}
          href={`/analytics/players/${pack}/${item.slug}`}
          style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "9px 0", borderBottom: "1px solid var(--rule)", fontSize: 14 }}
        >
          <span>{item.name}</span>
          <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{item.score}</span>
        </Link>
      ))}
      <div style={{ marginTop: 10, fontSize: 13, color: "var(--ink-3)" }}>
        Least alike:{" "}
        <Link href={`/analytics/players/${pack}/${antipode.slug}`}>{antipode.name}</Link>{" "}
        <span className="mono">{antipode.score}</span>
      </div>
      <p style={{ marginTop: 10, fontSize: 12.5, color: "var(--ink-3)", lineHeight: 1.5 }}>
        Cosine similarity over {fieldsUsed.length} shared fields in this pack -- {fieldsList}. Alike in these numbers only; not a ranking, not a prediction.
      </p>
      <Receipt sourceArtifact="webapp/public/data/showcase/entity_comparables.json" verdict="descriptive_only" label="descriptive_only" />
    </div>
  );
}

export default Comparables;
