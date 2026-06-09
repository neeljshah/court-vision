"""ROADMAP RUNNER -- the loop's "what to build next" cursor over the LIVE-AI vision.

Reads data/registry/roadmap.json (the vision broken into dependency-ordered milestones), shows status, and
picks the NEXT milestone the agentic loop should work: deps satisfied, status=pending, NOT human-gated, by
priority. The loop then applies the section-7.4 lever priority WITHIN that milestone and fans out agents.

Honesty classes gate what the loop may do autonomously:
  research / paper  -> loop builds (gated, default-OFF, paper-only). serve_human -> loop scaffolds paper, human
  ships the page. realmoney_human -> human-only; the loop NEVER places money (invariant 0.1.2).

  python scripts/team_system/roadmap.py            # status table + the next pickable milestone
  python scripts/team_system/roadmap.py --next     # just the next milestone id (for the loop)
"""
from __future__ import annotations
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROADMAP = os.path.join(ROOT, "data", "registry", "roadmap.json")
AUTONOMOUS = {"research", "paper"}                 # the loop may build these unattended
HUMAN_GATED = {"serve_human", "realmoney_human"}   # loop scaffolds paper at most; human ships/places


def load() -> dict:
    return json.load(open(ROADMAP, encoding="utf-8"))


def _done(m) -> bool:
    return m.get("status") == "done"


def status() -> dict:
    rm = load()
    by_id = {m["id"]: m for m in rm["milestones"]}
    out = []
    for m in rm["milestones"]:
        deps_done = all(_done(by_id[d]) for d in m.get("depends_on", []) if d in by_id)
        pickable = (m["status"] == "pending" and deps_done and m["honesty"] in AUTONOMOUS)
        scaffoldable = (m["status"] == "pending" and deps_done and m["honesty"] == "serve_human")
        out.append(dict(id=m["id"], title=m["title"], honesty=m["honesty"], status=m["status"],
                        deps=m.get("depends_on", []), deps_done=deps_done,
                        pickable=pickable, scaffold_paper_only=scaffoldable,
                        priority=m.get("priority", 3), lever_type=m.get("lever_type")))
    return dict(goal=rm["goal"], doc=rm["doc"], milestones=out)


def next_milestone():
    """The next milestone the loop should build: pickable (autonomous), deps done, highest priority."""
    s = status()
    cands = [m for m in s["milestones"] if m["pickable"]]
    if not cands:
        # nothing autonomous left -> surface the next human-gated scaffold (paper) if any
        cands = [m for m in s["milestones"] if m["scaffold_paper_only"]]
    if not cands:
        return None
    cands.sort(key=lambda m: (-m["priority"], m["id"]))
    return cands[0]


def set_status(mid: str, new_status: str) -> None:
    rm = load()
    for m in rm["milestones"]:
        if m["id"] == mid:
            m["status"] = new_status
    tmp = ROADMAP + ".tmp"
    json.dump(rm, open(tmp, "w", encoding="utf-8"), indent=2)
    os.replace(tmp, ROADMAP)


def main():
    s = status()
    if "--next" in sys.argv:
        nm = next_milestone()
        print(nm["id"] if nm else "NONE (converged or all human-gated)")
        return
    print(f"=== ROADMAP: {s['goal'][:90]}... ===")
    print(f"(detail: {s['doc']})\n")
    print(f"{'id':4s} {'st':10s} {'honesty':16s} {'deps':10s} {'pick':5s} title")
    for m in s["milestones"]:
        mark = "DONE" if m["status"] == "done" else ("WORK" if m["pickable"] else
               ("scaf" if m["scaffold_paper_only"] else ("blok" if not m["deps_done"] else m["status"][:4])))
        print(f"{m['id']:4s} {m['status']:10s} {m['honesty']:16s} {str(m['deps']):10s} {mark:5s} {m['title'][:54]}")
    nm = next_milestone()
    print(f"\nNEXT (loop builds this): {nm['id'] + ' - ' + nm['title'] if nm else 'NONE (converged)'}")
    print("autonomous=research/paper · serve_human=scaffold-paper-only · realmoney_human=human-only (loop never places money)")


if __name__ == "__main__":
    main()
