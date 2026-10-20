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
        <ul>
          {items.map((q) => (
            <li key={q.href}>{q.href.startsWith("/") ? <Link href={q.href}>{q.label}</Link> : <a href={q.href}>{q.label}</a>}</li>
          ))}
        </ul>
      ) : (
        <p>no other page in this build.</p>
      )}
    </div>
  );
}
