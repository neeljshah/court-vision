// WorkingPapers -- the three repository readouts (docs/papers/*.md) on the papers hub, each with
// its abstract (first three summary sentences), date and a link to the full text. Server-only.
import { githubDoc } from "@/components/shell/nav";
import type { WorkingPaper } from "@/lib/analytics/workingPapers.server";

export function WorkingPapers({ papers }: { papers: WorkingPaper[] }) {
  if (!papers.length) return null;
  return (
    <section className="wrap" aria-labelledby="working-papers-h" style={{ paddingBottom: 48 }}>
      <h2 id="working-papers-h" className="serif">Readouts against the market</h2>
      <p className="paper-sub">Three longer readouts from the repository. Each copies its numbers from committed files and names them.</p>
      <ul style={{ display: "grid", gap: 16, marginTop: 16, listStyle: "none", padding: 0 }}>
        {papers.map((p) => (
          <li key={p.file} className="paper-working" style={{ border: "1px solid var(--rule)", padding: 16 }}>
            <h3 className="serif"><a href={githubDoc(p.file)}>{p.title}</a></h3>
            <p style={{ color: "var(--ink-3)", fontSize: 13 }}>{p.date ? `${p.date} · ` : ""}<code>{p.file}</code></p>
            <p style={{ color: "var(--ink-2)", marginTop: 8 }}>{p.abstract}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
