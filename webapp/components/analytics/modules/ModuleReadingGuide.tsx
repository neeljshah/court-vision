export function ModuleReadingGuide({ howToRead }: { howToRead?: string }) {
  if (!howToRead?.trim()) return null;

  return <section className="mv-reading" aria-labelledby="module-reading-guide-title">
    <h2 id="module-reading-guide-title" className="overline">How to read this figure</h2>
    <p>{howToRead}</p>
  </section>;
}
