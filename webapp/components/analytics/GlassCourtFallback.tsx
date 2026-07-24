import type { CSSProperties } from "react";

// The Glass Court still frame. This is a plain (server-renderable) component: it
// is what every reduced-motion / no-WebGL / import-failed visitor sees, and it
// stands in during SSR before the 3D chunk mounts. Composition mirrors the
// three.js scene (slate wireframe court + one amber rising arc) so the swap to
// the live hero is seamless. Strokes use analytics tokens, so it is theme-aware.
export default function GlassCourtFallback({
  style,
  className,
}: {
  style?: CSSProperties;
  className?: string;
}) {
  return (
    <div
      className={className}
      role="img"
      aria-label="The Glass Court -- a translucent half-court, the still frame of the 3D hero"
      style={{
        position: "relative",
        width: "100%",
        aspectRatio: "4 / 3",
        borderRadius: 14,
        overflow: "hidden",
        background:
          "linear-gradient(160deg, var(--paper-raised) 0%, var(--paper-tint) 58%, var(--paper) 100%)",
        border: "1px solid var(--rule)",
        boxShadow: "var(--shadow-raise)",
        ...style,
      }}
    >
      <span
        style={{
          position: "absolute",
          left: 12,
          top: 12,
          zIndex: 2,
          font: "700 11px/1 var(--font-sans)",
          letterSpacing: "0.13em",
          textTransform: "uppercase",
          color: "var(--ink-3)",
        }}
      >
        The Glass Court
      </span>

      <svg
        viewBox="0 0 400 300"
        width="100%"
        height="100%"
        preserveAspectRatio="xMidYMid slice"
        style={{ position: "absolute", inset: 0 }}
        aria-hidden="true"
      >
        {/* slate wireframe etched into the glass */}
        <g style={{ stroke: "var(--accent)" }} fill="none" strokeWidth={1.2}>
          <polygon points="70,250 330,250 300,90 100,90" strokeOpacity={0.5} />
          <ellipse cx={200} cy={90} rx={70} ry={16} strokeOpacity={0.32} />
          <line x1={200} y1={90} x2={200} y2={250} strokeOpacity={0.32} />
          <ellipse cx={200} cy={170} rx={38} ry={9} strokeOpacity={0.32} />
        </g>
        {/* the single amber rising-line arc (the logo motif) */}
        <path
          d="M100,90 C160,60 240,60 300,90"
          style={{ stroke: "var(--signal)" }}
          strokeWidth={2.4}
          fill="none"
          strokeLinecap="round"
        />
        <circle cx={300} cy={90} r={3.2} style={{ fill: "var(--signal)" }} />
      </svg>

      <span
        style={{
          position: "absolute",
          right: 12,
          bottom: 12,
          font: "500 11px/1.3 var(--font-mono)",
          color: "var(--ink-3)",
          background:
            "color-mix(in srgb, var(--paper-raised) 82%, transparent)",
          padding: "4px 8px",
          borderRadius: 6,
          border: "1px solid var(--rule)",
        }}
      >
        3D lazy-loaded -- reduced-motion shows this still
      </span>
    </div>
  );
}
