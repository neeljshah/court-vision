type Observation = { oldest: string | null; newest: string | null; missing: number };

// Board numeric timestamps are Unix seconds; strings must include a timezone.
function boardTime(value: unknown): number | null {
  const time = typeof value === "number" ? value * 1000
    : typeof value === "string" && /^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/i.test(value)
      ? Date.parse(value) : NaN;
  return Number.isFinite(time) && Number.isFinite(new Date(time).getTime()) ? time : null;
}

export function getBoardObservation(values: unknown[]): Observation {
  const times = values.map(boardTime).filter((time): time is number => time !== null);
  return {
    oldest: times.length ? new Date(Math.min(...times)).toISOString() : null,
    newest: times.length ? new Date(Math.max(...times)).toISOString() : null,
    missing: values.length - times.length,
  };
}

function Timestamp({ value }: { value: string }) {
  return <time dateTime={value}>{value.slice(0, 19).replace("T", " ")} UTC</time>;
}

export function BoardObservation({ observation, loading }: {
  observation: Observation;
  loading: boolean;
}) {
  const { oldest, newest, missing } = observation;
  const range = oldest !== newest;
  return (
    <div className="font-data text-[11px] leading-relaxed text-muted-foreground" data-testid="board-observation">
      {loading ? "Loading board timestamps..." : oldest && newest ? (
        <>
          {range ? "Board timestamps: oldest known " : missing ? "Known board timestamp: " : "Board generated: "}
          <Timestamp value={oldest} />
          {range && <>; newest known <Timestamp value={newest} />.{missing === 0 && " Data age uses the oldest timestamp."}</>}
          {missing > 0 && <span className="block">{missing} board timestamp{missing === 1 ? "" : "s"} unavailable.</span>}
        </>
      ) : "Board timestamp unavailable"}
    </div>
  );
}
