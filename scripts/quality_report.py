"""Quality report: compute metrics from tracking_data.csv."""
import csv

try:
    rows = list(csv.DictReader(open('data/tracking_data.csv')))
except FileNotFoundError:
    print("ERROR: data/tracking_data.csv not found — run pipeline first")
    exit(1)

teams = set(r.get('team', '') for r in rows)
players = set(r.get('player_id', '') for r in rows)
shots = [r for r in rows if r.get('event') == 'shot']

# ID switches: same player_id switching teams
pid_teams = {}
for r in rows:
    pid = r.get('player_id', '')
    team = r.get('team', '')
    if pid and team and team != 'referee':
        pid_teams.setdefault(pid, set()).add(team)
switches = sum(1 for ts in pid_teams.values() if len(ts) > 1)

# Team separation: fraction of non-referee players consistently on one team
single_team = sum(1 for ts in pid_teams.values() if len(ts) == 1)
total_pids = len(pid_teams)
team_sep_pct = round(100 * single_team / max(1, total_pids), 1)

non_ref_rows = [r for r in rows if r.get('team') != 'referee']
print(f"Rows tracked:     {len(rows)}")
print(f"Unique players:   {len(players)}")
print(f"Teams detected:   {teams}")
print(f"Shots detected:   {len(shots)}")
print(f"ID switches:      {switches}")
print(f"Team separation:  {team_sep_pct}%")
print()
print("| Metric           | Value |")
print("|------------------|-------|")
print(f"| Rows tracked     | {len(rows)} |")
print(f"| Unique players   | {len(players)} |")
print(f"| Shots detected   | {len(shots)} |")
print(f"| ID switches      | {switches} |")
print(f"| Team separation  | {team_sep_pct}% |")
