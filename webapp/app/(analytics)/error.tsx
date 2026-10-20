"use client";

import Link from "next/link";
import type { CSSProperties } from "react";

const action: CSSProperties = {
  display: "inline-flex", alignItems: "center", minHeight: 44,
  borderRadius: 8, padding: "10px 16px", fontWeight: 600, fontSize: 14,
};

export default function AnalyticsError({ reset }: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <section className="wrap" role="alert" aria-labelledby="analytics-error-title"
      style={{ padding: "64px 24px", maxWidth: 680 }}>
      <p className="overline">View unavailable</p>
      <h1 id="analytics-error-title" className="serif" style={{
        fontSize: "clamp(2rem,4.6vw,3.2rem)", fontWeight: 500, lineHeight: 1.1,
        margin: "12px 0 16px", color: "var(--ink)",
      }}>Unable to display this view.</h1>
      <p style={{ color: "var(--ink-2)", fontSize: 17, lineHeight: 1.6, marginBottom: 28 }}>
        This analytics view could not be displayed. Try loading it again, or return to the analytics overview.
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        <button type="button" onClick={reset} style={{ ...action, cursor: "pointer",
          border: "1px solid transparent", color: "var(--accent-ink-on)", background: "var(--accent)",
        }}>Try again</button>
        <Link href="/" prefetch={false} style={{ ...action,
          color: "var(--accent)", border: "1px solid var(--rule-strong)",
        }}>Back to home</Link>
      </div>
    </section>
  );
}
