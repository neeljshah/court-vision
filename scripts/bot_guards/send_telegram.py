#!/usr/bin/env python3
"""send_telegram.py — thin CLI wrapper around telegram_alerter.send_alert."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.monitoring.telegram_alerter import send_alert

if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Alert"
    ok = send_alert(msg)
    sys.exit(0 if ok else 1)
