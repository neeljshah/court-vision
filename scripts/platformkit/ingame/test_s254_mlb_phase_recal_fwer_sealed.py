from datetime import datetime, timedelta, timezone

from scripts.platformkit.ingame import s254_mlb_phase_recal_fwer_sealed as s254


def _records():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    phases = ("early", "mid", "late")
    return [{"game_id": "KXMLBGAME-26JUL%02d1310TEXCLE" % (i + 1), "ts": (start + timedelta(days=i)).isoformat(),
             "phase_bucket": "%s|tied" % phases[i % 3], "phase": phases[i % 3], "margin": 0.0,
             "model_prob": 0.35 + 0.02 * (i % 4), "market_prob": 0.5, "outcome": float(i % 2)} for i in range(16)]


def test_s254_prereg_and_purged_callback_cover_every_state():
    prereg = s254.prereg_identity()
    source = s254.states(_records())
    predicted, evaluated = s254.callback_predictions(source)
    audit = s254.purge_log(source, evaluated)
    assert prereg["header_lines"] > 31
    assert s254._stamp(prereg["sealed_at_utc"]).tzinfo is not None
    assert s254._teams("KXMLBGAME-26JUL271810AZTB") == ("ARI", "TB")
    assert s254._teams("KXMLBGAME-26JUL271810CWSCLE") == ("CHW", "CLE")
    assert s254._teams("KXMLBGAME-26JUL071415MILSTLG1") == ("MIL", "STL")
    assert len(predicted) == len(evaluated) == len(source) == 16
    assert all(0.0 <= value <= 1.0 for value in predicted.values())
    assert len(audit) == 8
    assert all(row["n_train_after"] < row["n_train_before"] for row in audit)
    assert all(row["n_train_after"] == row["evaluated_n_train"] for row in audit)
    assert all(row["excluded_game_clusters"] for row in audit)
    assert {s254._replication_side(row["game_id"]) for row in _records()} <= {"primary", "replication"}
