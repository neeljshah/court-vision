// components/shell/NotFoundBody.tsx -- the 404 content: links to the six sections, plus an
// inline script that sends retired dynamic-family URLs (lib/redirects.ts PREFIX_REDIRECTS,
// e.g. an old /atlas/<pack>/<entity>/ link) to their new home instead of a dead end.
import Link from "next/link";
import { PREFIX_REDIRECTS, REDIRECTS } from "@/lib/redirects";
import { SITE_NAV } from "./nav";
import s from "./shell.module.css";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";
const EXACT = Object.fromEntries(Object.entries(REDIRECTS).map(([k, v]) => [k, v.to]));

const REDIRECT_JS = `(function(){var b=${JSON.stringify(BASE_PATH)},x=${JSON.stringify(EXACT)},f=${JSON.stringify(PREFIX_REDIRECTS)};var p=location.pathname;if(b&&p.indexOf(b)===0)p=p.slice(b.length);if(p.slice(-1)!=='/')p+='/';var to=x[p]||null;for(var i=0;!to&&i<f.length;i++){if(p.indexOf(f[i].from)===0&&p!==f[i].from)to=f[i].to;}if(to)location.replace(b+to);})();`;

export function NotFoundBody() {
  return (
    <section className={s.notFound} aria-labelledby="nf-title">
      <p>404: not found</p>
      <h1 id="nf-title">This page is not in the record.</h1>
      <p>
        The link is out of date or the page was retired. Nothing here is made up to fill the gap.
        These are the six sections of the site:
      </p>
      <ul>
        {SITE_NAV.map((item) => (
          <li key={item.href}>
            <Link href={item.href} prefetch={false}>{item.label}</Link>
          </li>
        ))}
      </ul>
      {/* eslint-disable-next-line react/no-danger */}
      <script dangerouslySetInnerHTML={{ __html: REDIRECT_JS }} />
    </section>
  );
}

export default NotFoundBody;
