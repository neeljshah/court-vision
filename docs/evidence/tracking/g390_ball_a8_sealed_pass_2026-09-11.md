VERDICT: NOT VALIDATED (adjudicated) -- ACCEPTANCE-1 readiness identity and B5 scratch-path clauses remain unmet; ACCEPTANCE-3 is repaired from archived predictions only. The single A8 allowance is spent; no follow-up inference or training is permitted.

# G390 -- ball fine-tune arm A8, the one sealed scoring pass

Preregistration: `docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/preregistration.md`; sealed at commit `9196b6de8` with SEAL sha256 `c27ad65d341eb336a6c5fe7c8fb1a412a685b3b86827b8f2285d74dd4944b261`, which predates scoring.
The sealed preregistration captured readiness digest `fe8bcbe...` before G389's landed correction changed that file to `d11a1c8c...`. The sealed file cannot be edited. This is a disclosed Q1 input-identity deviation; the actually loaded landed G389 bytes are named and hashed below.

## Measurement (unchanged; verifier reproduced twice)
A8: TP 90 / FP 169 / FN 212; C0 0.16393442622950818; Wilson95 lower 0.29211016505655896; ALL FP / N_absent 169/188 = 0.898936170212766. ABSENT-only false-call rate: 50/188 = 0.26595744680851063 (beside, never replacing, the sealed ALL-FP/N_absent result). A0: TP 0 / FP 8 / FN 302. All three sealed quality bars are missed.

## Fix 1c (2026-09-11)
Both codex-sol REJECTs found ACCEPTANCE-1's sealed-readiness mismatch, ACCEPTANCE-3's A0-omitted renders, and B5's `/workspace/g390_scratch` compute path. The readiness mismatch is adjudicated as a disclosed identity deviation because the preregistration is immutable; B5 is a disclosed process deviation because the sole run cannot repeat. The 30 renders are regenerated from the archived deployed-route A0 and archived A8 CSVs on the original native sheets, with no model load or inference. Old renders remain byte-preserved in `renders/pre_fix1c/`.

## Fix 1d (2026-09-11)
B2 restores `n_predictions` and `distance_720p` beside the newer render columns from `paired_frame_scores.csv`; ACCEPTANCE-3 refreshes the render manifest for current and historical bytes; Q1 names the preregistration path, commit, and seal. Measurement is unchanged; ACCEPTANCE-1 readiness and B5 remain adjudicated.

## NOT VERIFIED
- A8 repeatability, an additional candidate run, and a second token-gated score are not verified and are not allowed.
- A0 was not re-inferred; only its archived deployed-route predictions were rendered and re-scored.
- External weight availability and pod state are not verified; no deploy, flag, registry, or `data/` path changed.

## SHA-256 (refreshed changed evidence artifacts)
E47F7888A9739118D585C154C8D20AB3ACB3344B0D02347EA05633BD5EC9D81E scripts/platformkit/tracking/g390_render_archived.py
11DE7BB6C0B54DD62929CA31B4ED43CDC74808865135CB620C9E6ACB928DE761 tests/platformkit/test_g390_ball_a8_sealed_pass.py
2C03E82124AABE640DEA73018C4561034975A86F7B22FF17BB9EDC9B75FF4235 docs/evidence/tracking/G390_ADJUDICATION_2026-09-11.md
F0990C57AF91CB8B36B30DB1B7A4B1F914E7AC1B8C4C9D88E2F899905A0EFFE4 docs/evidence/tracking/RESULTS_LEDGER.md
85DE9943DBFAE8AC64FAC91F1B8BF14C24C98EFF038419543C08AAB8431881CB docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/renders_index.csv
2894438AED6EF004F99452F5BF1226C0B46E99A79D354EFE088A4D2625C6A4BA docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/sha256_manifest.txt
793E97B44A40978D4A7CE1D4947DB4207788E9ACCE1BCDE746E63FCB52A471FF docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_00_00256fbe30cd.jpg
5FA57FFE3895CA2642098749BE8B6F9EA7E08489F4FD42A9CD3C4AF93A2140DC docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_01_08037ac3f452.jpg
99F0EAF079AC0907BBFE4F2773FDD1DF0FB5A4F46F097C8376E4D16C8BA538EF docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_02_10b7527d0321.jpg
69FCCD96909609937FBE8C77E817CFA91EA770DD8D4671F85A24531EBE84590A docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_03_1d1cb6529078.jpg
53F717B123FCEB8A97DE64684702EAE646ED8B47460FC80E5535DD6A26E3A611 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_04_24896f416885.jpg
A7F037F2EB2408F2CAFEC96BCF877351A6C3BECC3574553E651CAED3EC66C169 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_05_2ce019929197.jpg
6E03D3541B22105980BD6D4095EC5B1D030CEEE74A50DD9D7293872FAFE613BA docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_06_3460c10d21ee.jpg
69240786267FBFFFBE0B127F1F25E2C6573829C0F44FE41279DF674EAC24754A docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_07_3ed0ff187412.jpg
03B0910AACF80EE0BBDB03812BA1BA0E81CC2F48D41C5D60D1AF46EAE5907474 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_08_470cd9afd8c5.jpg
AAF8651B26D60CB46741139DF117C74591BFDDBC318987AB51D0663DDEB0E396 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_09_4d4cfea838a0.jpg
A09135EF29302949C94E0E04123CD76C3893327BC0A541DE38B1CD508D85FBF0 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_10_55e1a59bf974.jpg
BD53CAC0D8B35FE6755F05F6432D591103C95735681A17636FB9C3A3E7AEE1BD docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_11_5ddd9b25dd62.jpg
1E805C03E41D2507A9680C1D2E48F5C4F46D6AB11D78CDFD919ABBA972D5E3DE docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_12_65082cf67f56.jpg
0166B1C9DF4ED328A7B8D425F19F3D367548E497113EC53849EFCFFCB18C07D7 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_13_6e9a9606a372.jpg
3E1E9EEFA4C2344D090863AA72F1DC325AB0555BDE53A3C3AB0CB7491C5342EA docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_14_77f595ac7e96.jpg
345B388810704F003239C5BA6313D9571D7C229C13F0B027A591F901290449F7 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_15_805123a819fe.jpg
1C1F88E37706C3F9AEEBA7C75B0C2D3EB9F13668E33A0650C56698A959F3F917 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_16_87e899b0a031.jpg
27DBBDEFA66BA008F5FB70FE66D1B26526DE7509FA76F25A8A7B36E242B3636C docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_17_91237c714d31.jpg
ABF0BC72AE1D50129A37C27F0C22AE76F3E179E3A6BEDB783AC1AE78842CB214 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_18_996c9c8a64da.jpg
444BA5DC34DEB4344460CCAC34CC3EA88A3CA6A33BA46F6189BEBFDFE9853DDC docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_19_a45b83a13ce2.jpg
9DDFF0ED05CAAA764A1575A1456E95D8C281B1F785636975E4DCD2E28AD38067 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_20_af3d55f58e9e.jpg
6469B1ACC75F4B06215F4CD51A0BD1B32571F1F3C7A7C390C78ABBB32CC96590 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_21_b716e12e42a7.jpg
A24C877F2A2F9AEE96FC2508030AE9D8F474C915139A34A9AF15379579F46E98 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_22_bfb8daf6db57.jpg
903D2CB3DD4C7A66175F0F6BDCF96B9F79D1ED60F33F17851DBE37927DB68A02 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_23_c8584a3adc7a.jpg
9DE21C18515A2D979BD10CAD2DC477F2E9B5EB7AB7CA4066845613DF327E975A docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_24_d20dae939d7d.jpg
968F3D26E65C7674E902DEBF449F41D83F18A1C92A6C2FDA7923DD5103920B0A docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_25_def4b74088e9.jpg
D3CE77FB8540F57216BA590D1A5D4C3E1306D383AC0D44A002FF959AF7857681 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_26_e5883851f448.jpg
7435C28BF940F0AA864E250BD76E4AF215758D2D164CC91E5445D64C4AA56B90 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_27_ec8f5ca63a7b.jpg
4B3BF4599A9B7C8B9D3FA102D51F90BC5D8A5FDB5925C2DA952BB79BC01B9F01 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_28_f77c3f33f4d7.jpg
AB5823630AEA2DC09C49928EB717CE8DF69A401657AF746BBA5EAF38C4C9B9D7 docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/renders/render_29_ff4169c59f81.jpg

Fix 1e (2026-09-11, orchestrator): the render-index generator now emits n_predictions and distance_720p beside the aliases and asserts the 9-column header (B2); memo hash refreshed. The verifier has declared the readiness-identity and scratch-route clauses UNCORRECTABLE after the single allowance; the row lands as NOT VALIDATED (adjudicated) per G390_ADJUDICATION.
