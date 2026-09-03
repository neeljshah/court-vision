"""S175 regression: T1 archive screen_p is indexed without changing raw_p."""
from types import SimpleNamespace

from scripts.platformkit import foundry_runner
from scripts.platformkit.foundry import results_db, tiers
from scripts.platformkit.foundry.grammar import Hypothesis


def test_s175_record_indexes_t1_archive_screen_p(tmp_path):
    """The construct denominator is its one recorded T1 result."""
    db_path = tmp_path / "s175.sqlite"
    trials_dir = tmp_path / "trials"
    hypothesis = Hypothesis("nba", "s175_feature", "raw", (), frozenset(), "pregame", "ml",
                            family="s175_family")
    with results_db.ResultsDB(db_path) as db:
        digest = db.upsert_hypothesis(hypothesis)
        queue = SimpleNamespace(db=db, corpus_sha="s175_corpus", trials_dir=trials_dir,
                                incumbent="p_base")
        result = tiers.TierResult(
            hash=digest, tier="T1", family="s175_family", corpus="nba", corpus_unit="unit",
            n=1, n_eff=1.0, brier_model=0.2, brier_close=0.21, dm=-0.3, raw_p=None,
            k_family=None, k_global=None, deflated_p=None, pbo=None, verdict="SCREEN",
            artifact_path="", screen_partition_sha256="screen", verdict_partition_sha256="verdict",
            cluster_key="team", screened_n=1, prereg_sha256="s175", spec_version="s175",
            archive={"screen_p": 0.125})
        foundry_runner._record(queue, result)
        row = db._c.execute("SELECT raw_p, screen_p, artifact_path FROM result").fetchone()
        assert tuple(row[:2]) == (None, 0.125)
        assert db.family_p_values("s175_family", tier="T1") == [0.125]
        assert db.family_p_values("s175_family") == []
    assert (trials_dir / "{0}_T1_unit.json".format(digest)).is_file()
