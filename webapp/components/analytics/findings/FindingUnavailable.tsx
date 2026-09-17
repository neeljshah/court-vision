import { artifactUrl } from "@/lib/analytics/artifactProvenance";
import { FindingsBackLink } from "./FindingsBackLink";

export function FindingUnavailable({ artifactId }: { artifactId?: string }) {
  const sourceHref = artifactId ? artifactUrl(`${artifactId}.json`) : null;
  return (
    <section aria-label="Finding unavailable" style={{ marginTop: 16, maxWidth: 700 }}>
      <p style={{ color: "var(--ink-2)" }}>Exhibit data not available in this build.</p>
      {sourceHref ? <p style={{ marginTop: 12 }}><a href={sourceHref}>Published source JSON</a></p> : null}
      <div style={{ marginTop: 16 }}><FindingsBackLink /></div>
    </section>
  );
}

export default FindingUnavailable;
