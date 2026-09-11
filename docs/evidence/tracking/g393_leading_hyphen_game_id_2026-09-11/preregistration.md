# G393 Preregistration

Scope: parser-only proposal review for the run_clip route. No live routing, tracking, rating, scoring, pod job, deployment, register, or results-record action is authorized.
Binding before-condition: extract the current `build_command` function from `scripts/platformkit/track_daemon.py` and all parser-construction statements in `scripts/run_clip.py`; replay their original argv without executing either main routine.
Construct universe: for i = 0..29, test `-Oa_BpdVT64_s` + str(1000+i) and `Oa_BpdVT64_s` + str(1000+i), with video/output paths containing spaces, `--frames 3000`, and `--no-show`.
Supplemental values: `--help`, `--frames`, `-1`, `-`, `--`, `-x=y`; each must be recovered as the game id without enabling help or changing frames.
Candidate: in an in-memory source copy only, replace the run_clip caller pair `--game-id`, game_id with the single argv token `--game-id=` + game_id. Preserve list argv and all other token bytes.
Acceptance: exact recovery for all 30 leading ids in the candidate, reproduction of original leading-id parser failures, identical ordinary-id namespaces, and unchanged unrelated arguments. Any drift rejects the proposal.
Evidence: source hashes, case inventory, argv and namespace cards, stderr/status records, caller census, source-proposal diff, and a prepare-only memo skeleton.
Sign convention: no loss delta or scored comparison is produced by this parser-only construct review.
SEAL sha256 4787b4c8477a66fe8427ca0d46e1ed5b9fafa4ec776972e05f74bfe976f20d6c
