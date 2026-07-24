// app/(analytics)/not-found.tsx -- analytics-scoped 404, rendered INSIDE the
// (analytics) root layout so it wears the Reading Room chrome (nav + footer), not
// the terminal's. Fires for notFound() in analytics segments (e.g. an unknown
// /analytics/m/<id>, which m/[id]/page.tsx calls) and unmatched /analytics/* nav.
// <Link> auto-prefixes basePath, so both links resolve under /court-vision. ASCII only.
import Link from "next/link";
import type { CSSProperties } from "react";

const heading: CSSProperties = {
  fontSize: "clamp(2.2rem,4.6vw,3.2rem)",
  fontWeight: 500,
  lineHeight: 1.08,
  letterSpacing: "-.02em",
  margin: "12px 0 16px",
  color: "var(--ink)",
};
const lede: CSSProperties = {
  color: "var(--ink-2)",
  fontSize: 17,
  lineHeight: 1.6,
  marginBottom: 28,
};
// inline-flex + min-height so the anchors meet the product's 44px touch standard
// (min-height is inert on a default-inline <a>).
const primaryBtn: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  minHeight: 44,
  borderRadius: 8,
  padding: "10px 16px",
  fontWeight: 600,
  fontSize: 14,
  color: "var(--accent-ink-on)",
  background: "var(--accent)",
};
const ghostBtn: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  minHeight: 44,
  borderRadius: 8,
  padding: "10px 16px",
  fontWeight: 600,
  fontSize: 14,
  color: "var(--accent)",
  border: "1px solid var(--rule-strong)",
};

export default function AnalyticsNotFound() {
  return (
    <section className="wrap" style={{ padding: "96px 24px", maxWidth: 680 }}>
      <p className="overline">404 &middot; not found</p>
      <h1 className="serif" style={heading}>
        This page is not in the record.
      </h1>
      <p style={lede}>
        The analytic, entity, or explainer you followed does not exist, or its link
        is out of date. Nothing here is fabricated to fill the gap.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        <Link href="/analytics" style={primaryBtn}>
          Back to Analytics home
        </Link>
        <Link href="/analytics/browse" style={ghostBtn}>
          Browse all analytics
        </Link>
      </div>
    </section>
  );
}
