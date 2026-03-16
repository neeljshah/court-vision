"""Temporary verification script for db.py — safe to delete after use."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.pop("DATABASE_URL", None)

from src.data.db import get_connection
print("Import OK")
try:
    get_connection()
    print("ERROR: should have raised ValueError")
    sys.exit(1)
except ValueError as e:
    print(f"ValueError raised correctly: {e}")
    sys.exit(0)
except Exception as e:
    print(f"Wrong exception type: {type(e).__name__}: {e}")
    sys.exit(1)
