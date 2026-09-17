import Link from "next/link";

/** A consistent return route for readers who land on a finding directly. */
export function FindingsBackLink() {
  return (
    <p style={{ maxWidth: 1120, margin: "0 auto", padding: "16px 24px 0", fontSize: 14, fontWeight: 600 }}>
      <Link href="/analytics/findings/">Findings</Link>
    </p>
  );
}

export default FindingsBackLink;
