// QuotedOnList -- renders the build-time "quoted on" list for one receipt's source artifact
// (lib/quotedOn.server). Server component; internal routes use next/link.
import Link from "next/link";
import { quotedOn } from "@/lib/quotedOn.server";

export function QuotedOnList({ artifact }: { artifact: string }) {
  const items = quotedOn(artifact);
  return (
    <div data-testid="quoted-on">
      <p><code>{artifact}</code> is quoted on:</p>
      {items.length ? (
        <ul style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", listStyle: "none", padding: 0 }}>
          {items.map((q) => (
            // 24px minimum touch target (axe target-size); the list is a chip row, not prose.
            <li key={q.href} style={{ minHeight: 24, display: "inline-flex", alignItems: "center" }}>
              {q.href.startsWith("/") ? (
                <Link href={q.href} style={{ padding: "4px 0", textDecoration: "underline" }}>{q.label}</Link>
              ) : (
                <a href={q.href} style={{ display: "inline-block", minWidth: 24, padding: "4px 0", textDecoration: "underline" }}>{q.label}</a>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p>no other page in this build.</p>
      )}
    </div>
  );
}
