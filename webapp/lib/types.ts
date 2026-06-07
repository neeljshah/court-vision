export type Bet = {
  game_id: string;
  player_id: string | number;
  name: string;
  team?: string;
  stat: string;
  side: "over" | "under";
  line: number;
  book: string;
  odds: number;
  projected_final: number;
  current?: number;
  delta?: number;
  ev: number;
  kelly: number;
  tier: "S" | "A" | "B" | "C";
  why?: string;
  reason?: string;
};

export type PBPEvent = {
  game_id: string;
  topic: string;
  action_number?: number;
  period?: number;
  clock?: string;
  description?: string;
  player_id?: number;
  player_name?: string;
  team_tricode?: string;
  score_home?: number;
  score_away?: number;
  ts?: number;
};

export type Snapshot = {
  game_id: string;
  game_status?: string;
  home_team?: string;
  away_team?: string;
  home_score?: number;
  away_score?: number;
  period?: number;
  clock?: string;
  players?: Array<{
    player_id?: number;
    name?: string;
    team?: string;
    min?: number;
    pts?: number;
    reb?: number;
    ast?: number;
    pf?: number;
  }>;
};

export type Projection = {
  player_id: number | string;
  name?: string;
  team?: string;
  stat: string;
  current?: number;
  projected_final: number;
  delta?: number;
  projection_source?: string;
  foul_factor?: number;
  blow_factor?: number;
  heat_check_shrinkage?: number;
  matchup_reason?: string;
};

export type BusMessage =
  | { topic: "hello"; event: HelloPayload; ts: number }
  | { topic: "pong"; event: Record<string, never>; ts: number }
  | { topic: "snapshot.updated"; event: { game_id: string; snapshot: Snapshot }; ts: number }
  | { topic: "projection.updated"; event: { game_id: string; rows: Projection[]; reason?: string; source?: string }; ts: number }
  | { topic: "bet.recommended"; event: Bet; ts: number }
  | { topic: "lines.refreshed"; event: { date: string; counts: Record<string, number> }; ts: number }
  | { topic: string; event: PBPEvent; ts: number };

export type HelloPayload = {
  snapshots: Record<string, Snapshot>;
  projections: Record<string, Projection[]>;
  recent_bets: Bet[];
  recent_alerts: { ts: number; severity: string; msg: string }[];
};

export type Explanation = {
  summary: string;
  sections: Array<{ kind: string; title: string; body: string }>;
};
