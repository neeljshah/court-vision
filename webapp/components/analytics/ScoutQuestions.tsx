// ScoutQuestions -- "Scout everywhere" footer (NIGHT_PLAN elevated goal).
// Every flagship page ends with up to 3 suggested questions, each a pill that
// deep-links into /analytics/ask?q=<prefill>. Server component; Next <Link>
// auto-prefixes basePath. Suggestions are drawn from the committed ask corpus
// by the caller -- this component only presents them.
import type { CSSProperties } from "react";
import Link from "next/link";

const pill: CSSProperties = {
  fontSize: 13,
  color: "var(--accent)",
  border: "1px solid var(--rule-strong)",
  borderRadius: "var(--radius-pill, 999px)",
  // min-height:44 (box-sizing:border-box globally) meets the 44px touch target;
  // inline-flex + center so the label sits mid-pill.
  display: "inline-flex",
  alignItems: "center",
  minHeight: 44,
  padding: "6px 14px",
  background: "var(--paper-raised)",
  textDecoration: "none",
  lineHeight: 1.35,
};

export function ScoutQuestions({
  questions,
  heading = "Ask Scout about this",
}: {
  questions: string[];
  heading?: string;
}) {
  const items = questions.filter(Boolean).slice(0, 3);
  if (items.length === 0) return null;

  return (
    <section
      aria-label="Suggested questions for Scout"
      style={{ marginTop: 32, paddingTop: 20, borderTop: "1px solid var(--rule)" }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 12,
        }}
      >
        <span
          aria-hidden
          style={{
            width: 18,
            height: 18,
            borderRadius: "50%",
            background: "var(--signal)",
            display: "grid",
            placeItems: "center",
            flex: "0 0 auto",
            opacity: 0.95,
          }}
        >
          <span style={{ color: "var(--paper)", fontSize: 8, lineHeight: 1 }}>
            {"\u25B2"}
          </span>
        </span>
        <span
          style={{
            fontWeight: 700,
            fontSize: 11,
            letterSpacing: "0.13em",
            textTransform: "uppercase",
            color: "var(--ink-3)",
          }}
        >
          {heading}
        </span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {items.map((q) => (
          <Link
            key={q}
            href={`/analytics/ask?q=${encodeURIComponent(q)}`}
            style={pill}
          >
            {q}
          </Link>
        ))}
        <Link
          href="/analytics/ask"
          style={{
            ...pill,
            border: "1px solid transparent",
            background: "transparent",
            fontWeight: 600,
          }}
        >
          {"Ask anything \u2192"}
        </Link>
      </div>
    </section>
  );
}

export default ScoutQuestions;
