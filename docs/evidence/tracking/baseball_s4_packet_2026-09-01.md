# Baseball S4 packet - 2026-09-01

## Claim

Baseball S4 is complete by the measured-impossibility branch: this is a
declared `image_px` corpus, not field-coordinate tracking.

## Field homography is impossible on the measured broadcast framing

`python -m scripts.platformkit.baseball_calib_probe` sampled two independent
1280x720 MLB centre-field clips (500 frames each, stride 3). The known 18-ft
mound chord gave lateral FOV p50 about 42 ft (26.9-42.3 ft observed, p95 66.2
ft). A 90-ft infield needs 127.28 lateral ft to jointly see first and third;
0/24 usable mound frames contained two bases. The score-bug-obscured mound
edge and merged home-plate dirt remove the alternative conic solve. These are
physical observability results, not harness tuning.

## Declared corpus

Command: `find data/tracking -path '*/npb*/*' -name tracking_data.csv`, then
`awk -F, 'NR>1 {seen[$1]=1} END {print length(seen)}'` and row counts. Only
content-gate-confirmed NPB files with `coordinate_space=image_px` are in:

`npb_01` 36,684/8,775; `npb_02` 43,025/9,396; `npb_04` 32,744/9,228;
`npb_09` 41,348/8,630; `npb_10` 43,625/9,259; `npb_2iFIuWxu6HI`
41,591/9,272; `npb_Arpw32zVTuc` 30,965/9,235; `npb_HQfhD5Iwm7U`
35,142/9,216; `npb_RIwbEjh-zTs` 36,367/9,242; `npb_V3FrwLVwCpA`
30,831/9,199; `npb_XGhDpaeFSKc` 33,729/9,038; `npb_YI146E0gNnA`
42,827/8,590; `npb_aEpT4HU_ilg` 34,836/9,002; `npb_dTLgOoX4nhc`
34,698/8,965; `npb_jm2Ocr-LAtc` 36,626/9,285; `npb_kqPv-_WwWLk`
24,431/9,087; `npb_wZgoTPoZXKM` 36,632/8,597 (rows/unique frames).
Total: 616,101 rows / 154,016 frames. `npb_03`, `npb_05`, `npb_06`,
`npb_07`, and `npb_08` are out: no image_px provenance. All MLB/KBO-prefixed
CSVs are out: their content has not passed the real-baseball gate.

## Identity measurement

`nice -n 15 /workspace/venvs/transnet/bin/python /tmp/transnet_npb16.py`
decoded 18,001 genuine NPB 720p frames at 30 fps and emitted 99 TransNetV2
boundaries (threshold 0.5; p50 shot 5.733 s). The matched current detector
emitted 113. With unchanged stride 3, `BaseballAdapter.process_video` emitted
the same 24,068 rows over 5,673 frames before/after: current 919 tracks,
median 19, churn 51.1, singleton share 7.07%; TransNet 654 tracks, median 21,
churn 36.3, singleton share 5.35%. Command:
`python -m scripts.platformkit.tracking_quality_scan /workspace/baseball_wave7_current.csv /workspace/baseball_wave7_transnet.csv`.

## Consumer contract

Consumers may use these rows for observed-pixel detector and temporal-identity
research. They may not compute field locations, field-space harness metrics,
or relabel pixels as feet/metres/homography output without a separately
validated calibration.
