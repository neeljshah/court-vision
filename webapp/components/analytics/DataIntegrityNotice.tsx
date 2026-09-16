import Link from "next/link";
import type { DataIntegrityNotice as Notice } from "@/lib/analytics/dataIntegrity";
import styles from "./DataIntegrityNotice.module.css";

export function DataIntegrityNotice({ notices, moduleIds }: { notices: readonly Notice[]; moduleIds?: readonly string[] }) {
  if (!notices.length) return null;
  const current = new Set(moduleIds);
  return <>
    {notices.map(notice => {
      const artifacts = moduleIds ? notice.affectedModules.filter(id => current.has(id)) : notice.affectedModules;
      return <aside className={styles.notice} aria-label="Data integrity" key={notice.id}>
        <p className={`overline ${styles.label}`}>Data integrity</p>
        <p className={styles.summary}>{notice.summary}</p>
        <ul className={`mono ${styles.artifacts}`} aria-label="Affected artifacts">
          {artifacts.map(id => <li key={id}>{id}</li>)}
        </ul>
        <Link className={styles.link} href={notice.detailRoute}>Read the full finding</Link>
      </aside>;
    })}
  </>;
}
