# S676 slo_status on the clone's tracked nights (reproduction artifact)

Command (trunk e1b3bcdc + branch cloud/S676-2026-09-30, re-run after fix round 1 with identical output, cloud Ubuntu clone, Python 3.11):
`python3 -m scripts.platformkit.ops.slo_status --end 2026-09-29 --days 14 --now 2026-09-30T12:00:00Z`

Inputs (full path, bytes, sha256):
- docs/evidence/forward/nights/2026-09-24.json 7213 89010ca0ecc5af12e8d155f18da12e9f89ace1fa5a8a4472e1ac9afb4989c86e
- docs/evidence/forward/nights/2026-09-25.json 6202 fec12c74bd26f04446c186bc38292f8bfe3af0398c28c520074d69ec947f91b6
- docs/evidence/forward/nights/2026-09-26.json 10920 ab9d880e2135859111c26b817a2251ab376adb327070d874d49ec01937df2ade
- docs/operations/paper_desk_config.json 6248 ea52bf3cc3ee94696ab97e1f0db606ecefd6431585398e9f294563cde49cd217 (legacy_noncanonical_nights, timeouts_s.night, night_not_before_utc)
- docs/evidence/forward/desk_health/: absent (no record exists yet; every slot day is unobserved)

Stored as .md because .gitignore:588 tracks only *.md under docs/evidence/harness/. Output verbatim:

```json
{
    "days": 14,
    "desk_epoch": "2026-09-24",
    "night_due_after_s": 29100,
    "not_due": [
        "2026-09-16",
        "2026-09-17",
        "2026-09-18",
        "2026-09-19",
        "2026-09-20",
        "2026-09-21",
        "2026-09-22",
        "2026-09-23"
    ],
    "now": "2026-09-30T12:00:00Z",
    "observations": [
        {
            "evidence": [
                "docs/evidence/forward/nights/2026-09-24.json"
            ],
            "kind": "night_yield_miss",
            "reason": "ValueError:night_noncanonical_as_of",
            "severity": "P1",
            "sport": "all",
            "subject": "2026-09-24",
            "verdict": "FAIL"
        },
        {
            "evidence": [
                "docs/evidence/forward/nights/2026-09-25.json"
            ],
            "kind": "night_yield_miss",
            "reason": "ValueError:night_noncanonical_as_of",
            "severity": "P1",
            "sport": "all",
            "subject": "2026-09-25",
            "verdict": "FAIL"
        },
        {
            "evidence": [
                "docs/evidence/forward/nights/2026-09-27.json"
            ],
            "kind": "night_yield_miss",
            "reason": "night_record_absent",
            "severity": "P1",
            "sport": "all",
            "subject": "2026-09-27",
            "verdict": "FAIL"
        },
        {
            "evidence": [
                "docs/evidence/forward/nights/2026-09-28.json"
            ],
            "kind": "night_yield_miss",
            "reason": "night_record_absent",
            "severity": "P1",
            "sport": "all",
            "subject": "2026-09-28",
            "verdict": "FAIL"
        },
        {
            "evidence": [
                "docs/evidence/forward/nights/2026-09-29.json"
            ],
            "kind": "night_yield_miss",
            "reason": "night_record_absent",
            "severity": "P1",
            "sport": "all",
            "subject": "2026-09-29",
            "verdict": "FAIL"
        }
    ],
    "schema": "S676.slo_status.v1",
    "sli": {
        "canonical_nights": {
            "attainment": 0.166667,
            "due": 6,
            "fraction": "1/6",
            "met": 1,
            "misses": [
                "2026-09-24",
                "2026-09-25",
                "2026-09-27",
                "2026-09-28",
                "2026-09-29"
            ],
            "nights": [
                {
                    "canonical": false,
                    "date": "2026-09-24",
                    "legacy_listed": true,
                    "legacy_ref": "S602",
                    "reason": "ValueError:night_noncanonical_as_of"
                },
                {
                    "canonical": false,
                    "date": "2026-09-25",
                    "legacy_listed": true,
                    "legacy_ref": "S602",
                    "reason": "ValueError:night_noncanonical_as_of"
                },
                {
                    "canonical": true,
                    "date": "2026-09-26",
                    "reason": "canonical"
                },
                {
                    "canonical": false,
                    "date": "2026-09-27",
                    "reason": "night_record_absent"
                },
                {
                    "canonical": false,
                    "date": "2026-09-28",
                    "reason": "night_record_absent"
                },
                {
                    "canonical": false,
                    "date": "2026-09-29",
                    "reason": "night_record_absent"
                }
            ],
            "target": "OWNER_TBD"
        },
        "heartbeat_fresh": {
            "attainment": 0.0,
            "due": 288,
            "fraction": "0/288",
            "met": 0,
            "target": "OWNER_TBD",
            "unobserved_days": [
                "2026-09-24",
                "2026-09-25",
                "2026-09-26",
                "2026-09-27",
                "2026-09-28",
                "2026-09-29"
            ]
        },
        "tick_ok": {
            "attainment": 0.0,
            "due": 288,
            "fraction": "0/288",
            "met": 0,
            "target": "OWNER_TBD",
            "unobserved_days": [
                "2026-09-24",
                "2026-09-25",
                "2026-09-26",
                "2026-09-27",
                "2026-09-28",
                "2026-09-29"
            ]
        }
    },
    "window": [
        "2026-09-16",
        "2026-09-29"
    ]
}
```
