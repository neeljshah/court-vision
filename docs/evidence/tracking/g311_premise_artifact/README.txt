G311 premise artifacts, verbatim pod output.

Files were fetched from the pod as *.log and renamed to *.txt only because
.gitignore line 181 ignores *.log; contents are otherwise unmodified except
that 84 non-ASCII code points (pip progress-bar glyphs) in g311_premise.txt
(44) and g311_premise2.txt (40) were replaced with '?' to honour the
ASCII-only rail. No numeric value, version string, URL or error message was
touched by that replacement.

  g311_premise.txt              attempt 1: base env, constraints, route (i)
                                first failure (pkg_resources), route (ii)
                                install, the four 404 ONNX probes
  g311_premise2.txt             attempt 1 retry: mmengine/mmcv/mmdet resolved
                                versions, checkpoint fetch + SHA-256
  g311_premise3.txt             mmcv==2.1.0 build killed at its 780 s box
  route_i3_mmcv210_build.txt    that build's full pip log
  g311_premise4.txt             ATTEMPT 2: the same build run to a terminal
                                outcome, no artificial box
  route_i4_mmcv210_build.txt    attempt 2's full pip log
  g311_premise5.txt             ATTEMPT 2, a SECOND and INDEPENDENT build of the
                                same mmcv==2.1.0, run concurrently by another lane
                                into a separate prefix (/workspace/mmlab_env) with
                                TORCH_CUDA_ARCH_LIST=8.6. Different wheel bytes from
                                premise4's; BOTH reached the import gate.
  route_i5_mmcv210_build.txt    that second build's full pip log
  g311_run_a2b.txt              ATTEMPT 2: the harness run itself (both arms, three
                                games), warning lines stripped
  g311_summary_attempt2.json    ATTEMPT 2: the harness's own JSON output (the
                                per-game proxy numbers the memo tabulates)
  probes_verbatim.txt           every nvidia-smi / du / dd / sha256sum probe
