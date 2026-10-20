// paperLinks.ts -- the href of a /paper/<betId> execution-detail page.
//
// Two static-export facts shape it. The export writes /paper/<encoded id>/ with
// the percent-encoded id as the literal directory name, so the href must encode
// the id a second time (the browser decodes one layer before the host looks the
// directory up; a single-encoded href 404s on GitHub Pages). And Next strips the
// trailing slash from any link whose last segment contains a dot -- every id has
// one (a microsecond timestamp, "St. Louis") -- which would leave the page
// depending on a host redirect; encoding the dots keeps the slash, and the host
// decodes %2E back to "." when it resolves the directory. Live mode decodes the
// param once either way.
export function paperDetailHref(betId: string): string {
  return `/paper/${encodeURIComponent(betId).replace(/\./g, "%2E")}/`;
}
