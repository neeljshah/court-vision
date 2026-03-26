"""
new_session.py — SessionStart hook.
Creates or updates today's session note in vault/Sessions/.
"""
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = PROJECT_DIR / "vault" / "Sessions"


def main():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    note_path = SESSIONS_DIR / f"Session-{today}.md"

    if note_path.exists():
        print(f"Session note already exists: Session-{today}.md")
        return

    content = f"""# Session {today}

## Goals


## Notes


## Files Changed


## Issues Closed


## Issues Opened

"""
    note_path.write_text(content, encoding="utf-8")
    print(f"Session note created: Session-{today}.md")


if __name__ == "__main__":
    main()
