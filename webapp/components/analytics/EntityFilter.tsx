"use client";

function applyFilter(query: string) {
  const items = document.querySelectorAll<HTMLElement>("[data-name]");
  const sections = document.querySelectorAll<HTMLElement>(".pl-fsec");
  const normalized = query.toLowerCase().trim();
  items.forEach((item) => {
    item.style.display = !normalized || item.dataset.name?.includes(normalized) ? "" : "none";
  });
  sections.forEach((section) => {
    const matches = [...section.querySelectorAll<HTMLElement>("[data-name]")].some((item) => item.style.display !== "none");
    section.style.display = matches ? "" : "none";
  });
}

export function EntityFilter() {
  return <input
    id="plsearch"
    type="search"
    className="pl-search"
    placeholder="Filter entities by name..."
    aria-label="Filter entities by name"
    autoComplete="off"
    onChange={(event) => applyFilter(event.currentTarget.value)}
  />;
}
