"""
finalize_session.py — Stop hook.
Appends a "Session ended" timestamp to today's session note.
"""
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = PROJECT_DIR / "vault" / "Sessions"


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    note_path = SESSIONS_DIR / f"Session-{today}.md"
    if not note_path.exists():
        return
    timestamp = datetime.now().strftime("%H:%M")
    content = note_path.read_text(encoding="utf-8")
    if "Session ended" not in content:
        content += f"\n---\n_Session ended {timestamp}_\n"
        note_path.write_text(content, encoding="utf-8")
    print(f"Session finalized at {timestamp}")


if __name__ == "__main__":
    main()
