function validDay(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function PaperReportedDate({ value }: { value: unknown }) {
  return validDay(value) ? <time dateTime={value}>{value}</time> : <>unavailable</>;
}

export function PaperSourceTime({ value }: { value: unknown }) {
  if (typeof value !== "string" ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) ||
      !validDay(value.slice(0, 10))) return <>unavailable</>;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return <>unavailable</>;
  const iso = date.toISOString();
  return <time dateTime={iso}>{iso.slice(0, 19).replace("T", " ")} UTC</time>;
}
