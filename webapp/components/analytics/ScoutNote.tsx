// ScoutNote -- Tier-1 AI presence (DESIGN Sec. 5). A precomputed, receipt-cited
// insight annotation. NOT generated at runtime: one envelope read from committed
// JSON. NO_DATA is first-class -- shown, never hidden. Server component.
import type { CSSProperties, ReactNode } from "react";
import { Receipt, type ReceiptData } from "./Receipt";
import { typeset } from "@/lib/analytics/format";

export type ScoutStatus = "ok" | "descriptive_only" | "no_data";

export interface ScoutEnvelope {
  status: ScoutStatus;
  prose: string;
  chips?: ReceiptData[];
}

const NO_DATA_PROSE = "Scout has no verified read on this yet.";

// Lightweight, injection-safe emphasis: **bold** segments -> <strong>. Renders
// the mockup's bolded numerals without dangerouslySetInnerHTML. No-op on plain
// prose. ponytail: text-split only; add real markdown when a page needs it.
function renderProse(text: string): ReactNode[] {
  return text.split(/\*\*(.+?)\*\*/g).map((seg, i) =>
    i % 2 === 1 ? (
      <strong key={i} style={{ color: "var(--ink)", fontWeight: 600 }}>
        {seg}
      </strong>
    ) : (
      <span key={i}>{typeset(seg)}</span>
    )
  );
}

function Glyph({ neutral }: { neutral: boolean }) {
  return (
    <span
      aria-hidden
      style={{
        width: 26,
        height: 26,
        borderRadius: "50%",
        background: neutral ? "var(--null)" : "var(--signal)",
        display: "grid",
        placeItems: "center",
        flex: "0 0 auto",
        opacity: 0.95,
      }}
    >
      <span
        style={{
          color: "var(--paper)",
          fontSize: 11,
          lineHeight: 1,
          transform: "translateY(-1px)",
        }}
      >
        {"\u25B2"}
      </span>
    </span>
  );
}

export function ScoutNote({ envelope }: { envelope: ScoutEnvelope }) {
  const noData = envelope.status === "no_data";
  const prose = noData ? envelope.prose || NO_DATA_PROSE : envelope.prose;
  const chips = noData ? [] : envelope.chips || [];

  const wrap: CSSProperties = {
    background: "var(--paper-tint)",
    borderLeft: `2px solid ${noData ? "var(--null)" : "var(--accent)"}`,
    borderRadius: "var(--radius-card, 10px)",
    padding: "18px 20px",
    display: "flex",
    gap: 14,
    marginTop: 28,
  };

  return (
    <aside style={wrap} aria-label="Scout note">
      <Glyph neutral={noData} />
      <div style={{ minWidth: 0 }}>
        <span
          style={{
            display: "block",
            marginBottom: 4,
            fontWeight: 700,
            fontSize: 11,
            letterSpacing: "0.13em",
            textTransform: "uppercase",
            color: "var(--ink-3)",
          }}
        >
          Scout
        </span>
        <p
          style={{
            margin: 0,
            fontFamily: "var(--font-sans)",
            fontSize: 15,
            lineHeight: 1.6,
            color: "var(--ink-2)",
          }}
        >
          {renderProse(prose)}
        </p>
        {chips.length > 0 ? (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "6px 16px",
              marginTop: 10,
            }}
          >
            {chips.map((c, i) => (
              <Receipt key={`${c.sourceArtifact}-${i}`} {...c} />
            ))}
          </div>
        ) : null}
      </div>
    </aside>
  );
}

export default ScoutNote;
