// app/not-found.tsx -- the site 404 (exports to out/404.html). It renders under the bare
// root layout (no group stylesheet), so it carries the shared shell itself; the body also
// forwards retired dynamic-family URLs to their new home (lib/redirects.ts).
import type { Metadata } from "next";
import { SiteHeader } from "@/components/shell/SiteHeader";
import { SiteFooter } from "@/components/shell/SiteFooter";
import { NotFoundBody } from "@/components/shell/NotFoundBody";
import { snapshotDates } from "@/components/shell/snapshot.server";
import s from "@/components/shell/shell.module.css";

export const metadata: Metadata = { title: "Not found", robots: { index: false } };

export default function NotFound() {
  return (
    <div className={s.page}>
      <SiteHeader />
      <main id="main-content" tabIndex={-1}>
        <NotFoundBody />
      </main>
      <SiteFooter dates={snapshotDates()} />
    </div>
  );
}
