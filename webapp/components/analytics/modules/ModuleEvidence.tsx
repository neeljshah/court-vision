import Link from "next/link";
import { MovementEvidence } from "@/components/analytics/movement-evidence/MovementEvidence";
import { RestAsymmetryPanel } from "@/components/analytics/novel/RestAsymmetryPanel";
import { destinationForSourceModule } from "@/lib/analytics/analysisDestinations";
import type { ModuleEvidence as Evidence } from "@/lib/analytics/moduleEvidence";
import { loadMovementEvidence } from "@/lib/analytics/movementEvidence.server";

export function ModuleEvidence({ evidence, moduleId }: { evidence: Evidence; moduleId?: string }) {
  const inspector = moduleId ? destinationForSourceModule(moduleId) : undefined;
  const movement = moduleId === "market_overreaction" || moduleId === "micro_absorption" ? loadMovementEvidence() : null;
  // This artifact publishes `panels`, not the flat `results` the generic novel-stat renderer reads.
  const restAsymmetry = moduleId === "novel_rest_asymmetry";
  if (evidence.availability === "published" && !evidence.analyses.length && !inspector && !movement && !restAsymmetry) return null;
  return <section className="module-evidence" aria-label="Published evidence status">
    {evidence.availability === "unavailable" && <div className="module-evidence-finding"><p className="overline">Published finding</p><p>{evidence.headline}</p>{evidence.missingInputs.length ? <p><b>Missing input:</b> {evidence.missingInputs.join(", ")}.</p> : null}</div>}
    {evidence.availability === "partial" ? <div><p className="overline">Published coverage</p><p>{evidence.headline}</p>{evidence.coverage.length ? <table><thead><tr><th>Population</th><th>Status</th><th>Games</th><th>Usable buckets</th><th>Published reason</th></tr></thead><tbody>{evidence.coverage.map(row => <tr key={row.population}><td>{row.population}</td><td>{row.status.replace(/_/g, " ")}</td><td>{row.nGamesTotal ?? "-"}</td><td>{row.nBucketsUsable ?? "-"}</td><td>{row.reason || "-"}</td></tr>)}</tbody></table> : null}</div> : null}
    {movement && moduleId === "market_overreaction" ? <MovementEvidence kind="market_overreaction" evidence={movement.overreaction} /> : null}
    {movement && moduleId === "micro_absorption" ? <MovementEvidence kind="micro_absorption" evidence={movement.absorption} /> : null}
    {restAsymmetry ? <RestAsymmetryPanel /> : null}
    {evidence.analyses.length || inspector ? <div className="module-evidence-links"><p className="overline">Continue with the data</p>{inspector ? <Link href={inspector.route}>Open the interactive inspector: {inspector.title}</Link> : null}{evidence.analyses.map(analysis => <Link key={analysis.id} href={`/analytics/research/${analysis.id}`}>Open the interactive analysis: {analysis.title}</Link>)}</div> : null}
    <style>{`.module-evidence{margin:22px 0;border:1px solid var(--rule);border-radius:var(--radius-card);background:var(--paper-raised);padding:18px 20px}.module-evidence-finding{border-left:3px solid var(--signal);padding-left:14px}.module-evidence p{font-size:14px;line-height:1.55;color:var(--ink-2);margin:6px 0}.module-evidence b{color:var(--ink)}.module-evidence table{width:100%;border-collapse:collapse;font-size:12px}.module-evidence th,.module-evidence td{text-align:left;vertical-align:top;padding:7px 8px 7px 0;border-bottom:1px solid var(--rule)}.module-evidence th{font-family:var(--font-mono);font-weight:500;color:var(--ink-3)}.module-evidence-links{display:flex;flex-direction:column;gap:8px;margin-top:16px}.module-evidence-links a{color:var(--accent);font-size:14px}@media(max-width:620px){.module-evidence{overflow-x:auto}.module-evidence table{min-width:560px}}`}</style>
  </section>;
}
