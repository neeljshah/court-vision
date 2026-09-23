import type { TennisSurfaceFoldGroup } from "@/lib/analytics/tennisSurfaceFolds";
import { sourceUrl } from "@/lib/analytics/dashboardTypes";

const score = (value: number | null) => value === null ? "Unavailable" : value.toFixed(6);
const count = (value: number | null) => value === null ? "Unavailable" : value.toLocaleString("en-US");
const difference = (value: number | null) => value === null ? "Unavailable" : `${value > 0 ? "+" : ""}${value.toFixed(6)}`;

export function TennisSurfaceFoldPanel({ groups }: { groups?: TennisSurfaceFoldGroup[] }) {
  if (!groups?.length) return null;
  const total = groups.reduce((sum, group) => sum + group.rows.length, 0);
  return <details className="distribution-method">
    <summary>Inspect {total} held-out fold results</summary>
    <section aria-label="Published tennis surface-prior folds">
      <h3>Surface-specific versus surface-blind priors</h3>
      <p>Each table keeps one tour separate. Lower Brier means lower squared probability error; a positive surface-minus-blind difference means higher error for the surface-specific variant.</p>
      {groups.map(group => <section key={group.tour} aria-label={`${group.tour.toUpperCase()} fold results`}>
        <h4>{group.tour.toUpperCase()}</h4>
        {group.rows.length ? <div className="cv-table-scroll" role="region" tabIndex={0} aria-label={`${group.tour.toUpperCase()} fold measurements`}>
          <table className="cv-benchmark-table">
            <caption>{group.tour.toUpperCase()} held-out folds: published Brier scores and test-state counts</caption>
            <thead><tr><th scope="col">Source fold</th><th scope="col">Test states</th><th scope="col">Surface-blind Brier</th><th scope="col">Surface-specific Brier</th><th scope="col">Surface minus blind</th><th scope="col">Source row</th></tr></thead>
            <tbody>{group.rows.map(row => <tr key={row.sourceIndex}>
              <th scope="row">{count(row.fold)}</th><td>{count(row.testStates)}</td><td>{score(row.blindBrier)}</td><td>{score(row.surfaceBrier)}</td><td>{difference(row.delta)}</td>
              <td><details><summary>Source path</summary><code>{row.sourcePath}</code></details></td>
            </tr>)}</tbody>
          </table>
        </div> : <p>No fold rows are published for this tour.</p>}
      </section>)}
      <p>Differences subtract the two rounded scores published for the same fold. Scores and differences remain in Brier units. Test states can include repeated observations of a match; independent game counts and calendar test dates are not published here.</p>
      <p>Fold identifiers and order follow the source. These full-receipt tables do not change with the main analysis search; the summary CSV contains the tour rows. The recorded surface-prior comparison was rejected. The fold display does not establish a general surface effect or a new validation result.</p>
      <a href={sourceUrl("tennis_showcase")} target="_blank" rel="noreferrer">Inspect the published tennis fold source</a>
    </section>
  </details>;
}
