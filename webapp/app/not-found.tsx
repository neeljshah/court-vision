// app/not-found.tsx -- the site 404 (exports to out/404.html). It renders under the bare
// root layout (no group stylesheet), so it carries the shared shell itself; the body also
// forwards retired dynamic-family URLs to their new home (lib/redirects.ts).
import type { Metadata } from "next";
import { SiteHeader } from "@/components/shell/SiteHeader";
import { SiteFooter } from "@/components/shell/SiteFooter";
import { NotFoundBody } from "@/components/shell/NotFoundBody";
import { snapshotDates } from "@/components/shell/snapshot.server";
import { SITE_NAME, defaultOgImage } from "@/lib/seo/meta";
import s from "@/components/shell/shell.module.css";

// noindex and no canonical: a 404 has no URL of its own. og/twitter tags so a shared dead link still
// renders the site card with this page's title rather than the root defaults.
export const metadata: Metadata = {
  title: "Not found",
  description: "No page lives at this address. Retired routes forward to their new home; everything else is one click away in the site map.",
  robots: { index: false, follow: true },
  openGraph: { type: "website", siteName: SITE_NAME, images: [defaultOgImage()] },
  twitter: { card: "summary_large_image", images: [defaultOgImage().url] },
};

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
