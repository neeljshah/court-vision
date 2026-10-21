import { Receipt } from "@/components/analytics/Receipt";

// The staged atlas manifests live beside the other showcase JSON; the per-entity cards
// stamp the same path, so a reader lands on the same artifact from either surface.
export const SHOWCASE_REPO = "webapp/public/data/showcase";

type Props = {
  heading: string;
  color: string;
  count: number;
  asOf?: string;
  manifest: string;
  headingId?: string;
};

// Shared heading for the atlas and calibration pack sections on the entities index:
// name, card count, the pack's as-of date, and a Receipt that opens the staged manifest
// every row in the table is read from (the component and date format the entity cards use).
export function PackSectionHeading({ heading, color, count, asOf, manifest, headingId }: Props) {
  return <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 6, flexWrap: "wrap" }}>
    <span aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: color }} />
    <h2 id={headingId} className="serif" style={{ fontWeight: 500, fontSize: 26 }}>{heading}</h2>
    <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{count.toLocaleString()} cards{asOf ? ` \u00B7 as of ${asOf}` : ""}</span>
    <Receipt sourceArtifact={`${SHOWCASE_REPO}/${manifest}`} asOf={asOf} verdict="descriptive_only" label="descriptive_only" />
  </div>;
}
