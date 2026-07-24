// app/(analytics)/loading.tsx -- group-level Suspense fallback (Reading Room).
// ponytail: the shipped analytics surfaces are build-time static (output:'export'),
// so this rarely paints; it exists for client route transitions and any future async
// segment. Calm paper skeleton, reduced-motion-safe via analytics.css's global rule.
import type { CSSProperties } from "react";

const bar = (w: string, h: number, mt = 0): CSSProperties => ({
  width: w,
  height: h,
  marginTop: mt,
});

export default function AnalyticsLoading() {
  return (
    <div className="wrap" role="status" aria-busy="true" style={{ padding: "48px 24px" }}>
      <div className="a-skel" style={bar("40%", 18)} />
      <div className="a-skel" style={bar("72%", 44, 16)} />
      <div className="a-skel" style={bar("100%", 220, 32)} />
      <div className="a-skel-grid">
        <div className="a-skel" style={bar("100%", 160)} />
        <div className="a-skel" style={bar("100%", 160)} />
      </div>
      <span className="sr-only">Loading analytics...</span>
      {/* Collapse to one column below 820px like the real module page (mv-grid), so the
          fixed 320px column never overflows a phone. minmax(0,1fr) keeps the flex col
          from forcing a sideways scroll. */}
      <style>{`.a-skel-grid{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:32px;margin-top:32px}@media(max-width:820px){.a-skel-grid{grid-template-columns:minmax(0,1fr)}}`}</style>
    </div>
  );
}
