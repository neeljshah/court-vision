// components/shell/RedirectStub.tsx -- a static redirect page for a retired route (the
// export has no server redirects): meta refresh + canonical link + a visible "moved" link.
// The map lives in lib/redirects.ts; a stub page is three lines:
//   export const metadata = stubMetadata("/today/");
//   export default function Page() { return <RedirectStub from="/today/" />; }
import type { Metadata } from "next";
import Link from "next/link";
import { REDIRECTS } from "@/lib/redirects";
import { stubMeta } from "@/lib/seo/families";
import s from "./shell.module.css";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";

function target(from: string) {
  const r = REDIRECTS[from];
  if (!r) throw new Error(`RedirectStub: ${from} is not in lib/redirects.ts`);
  return r;
}

/** noindex,follow + canonical on the destination + og/twitter tags (lib/seo/families stubMeta). */
export function stubMetadata(from: string): Metadata {
  const r = target(from);
  return stubMeta(from, r.to, r.label);
}

export function RedirectStub({ from }: { from: string }) {
  const r = target(from);
  return (
    <section className={s.notFound} aria-labelledby="moved-title">
      {/* React 18 leaves this in body; browsers still honor a body meta refresh. */}
      <meta httpEquiv="refresh" content={`0; url=${BASE_PATH}${r.to}`} />
      <h1 id="moved-title">This page moved</h1>
      <p>It now lives under {r.label}.</p>
      <p>
        <Link href={r.to} prefetch={false}>Go to {r.label}</Link>
      </p>
    </section>
  );
}

export default RedirectStub;
