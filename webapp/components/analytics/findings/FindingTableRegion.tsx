import type { CSSProperties, ReactNode } from "react";
import styles from "./FindingTableRegion.module.css";

export function FindingTableRegion({
  label,
  children,
  style,
}: {
  label: string;
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <div
      role="region"
      tabIndex={0}
      aria-label={`${label} scroll horizontally`}
      data-scroll-region
      className={styles.region}
      style={style}
    >
      {children}
      <p className={styles.cue}>Scroll horizontally for all columns.</p>
    </div>
  );
}

export default FindingTableRegion;
