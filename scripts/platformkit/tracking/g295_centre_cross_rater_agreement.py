"""Local paired centre-cross reproducibility measurement; no production callers."""

import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Sequence

CATEGORIES = tuple('ABCDEFG')
LABELS = ("PLAYER'S FEET", "PLAYER'S BODY not feet", 'BARE COURT OR FLOOR',
          'BROADCAST GRAPHIC OR SCORE TICKER', 'PERSON not a player in play',
          'SOMETHING ELSE', 'CANNOT JUDGE')
SEAL = '886d98ae64a145d05b95f05ed1fd58a950fb67e3'
BASE = Path('docs/evidence/tracking')
OWN = BASE / 'g295_centre_cross_rater_agreement_artifact'
REF = BASE / 'g287_unconditioned_footpoint_content_artifact/blind_verdicts.csv'


def agreement(reference: Sequence[str], second: Sequence[str]) -> dict:
    """Compute seven-class kappa and multinomial delta-method standard error."""
    if not reference or len(reference) != len(second):
        raise ValueError('Nonempty paired vectors of equal length required')
    matrix = [[0] * 7 for _ in range(7)]
    for a, b in zip(reference, second):
        matrix[CATEGORIES.index(a)][CATEGORIES.index(b)] += 1
    n = len(reference)
    rows = [sum(row) for row in matrix]
    cols = [sum(matrix[i][j] for i in range(7)) for j in range(7)]
    r, c = [v / n for v in rows], [v / n for v in cols]
    po = sum(matrix[i][i] for i in range(7)) / n
    pe = sum(x * y for x, y in zip(r, c))
    if pe == 1:
        raise ValueError('Kappa undefined for a single constant shared category')
    kappa = (po - pe) / (1 - pe)
    # Unconstrained gradient d kappa / d p_ij, contracted with
    # multinomial covariance (diag(p) - p p.T) / n.
    gradients = [
        (matrix[i][j] / n,
         ((i == j) * (1 - pe) - (1 - po) * (c[i] + r[j])) / (1 - pe) ** 2)
        for i in range(7) for j in range(7)
    ]
    mean_g = sum(p * g for p, g in gradients)
    variance = sum(p * (g - mean_g) ** 2 for p, g in gradients) / n
    se = math.sqrt(max(0.0, variance))
    per_category = []
    for i, name in enumerate(CATEGORIES):
        both = matrix[i][i]
        total = rows[i] + cols[i]
        per_category.append(dict(
            category=name, reference_n=rows[i], second_n=cols[i], both_n=both,
            positive_agreement=2 * both / total if total else None,
            reference_retention=both / rows[i] if rows[i] else None,
            second_overlap=both / cols[i] if cols[i] else None,
            binary_agreement=(n - rows[i] - cols[i] + 2 * both) / n,
        ))
    return dict(n=n, categories=CATEGORIES, matrix=matrix,
                reference_marginal=rows, second_marginal=cols,
                raw_agreement=po, chance_agreement=pe, kappa=kappa,
                kappa_se=se, kappa_nominal_wald_95=[kappa-1.96*se, kappa+1.96*se],
                per_category=per_category)


def paired_player(reference: Sequence[str], second: Sequence[str]) -> dict:
    """Exact two-sided McNemar test of paired on-a-player (A+B) indicator judgments."""
    if len(reference) != len(second) or len(reference) < 2:
        raise ValueError('At least two equal-length paired observations required')
    lost = sum(a in ('A', 'B') and b not in ('A', 'B') for a, b in zip(reference, second))
    gained = sum(a not in ('A', 'B') and b in ('A', 'B') for a, b in zip(reference, second))
    discordant = lost + gained
    p = min(1.0, 2 * sum(math.comb(discordant, k)
                        for k in range(min(lost, gained) + 1)) / 2 ** discordant)
    n = len(reference)
    delta = (gained - lost) / n
    se = math.sqrt((discordant - n * delta ** 2) / (n * (n - 1)))
    return dict(n=n, reference_player_second_nonplayer=lost,
                reference_nonplayer_second_player=gained, discordant_n=discordant,
                nominal_exact_two_sided_p=p, second_minus_reference=delta,
                paired_delta_se=se, nominal_paired_wald_95=[delta-1.96*se, delta+1.96*se])


def manifest(path: Path, resolution: list[int] | None = None) -> dict:
    """Record exact input identity; non-image resolution is inapplicable."""
    return dict(path=path.resolve().as_posix(), bytes=path.stat().st_size,
                resolution=resolution, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def run() -> dict:
    """Verify the seal and full crop set, then archive all paired measurements."""
    for name in ('blind_order.json', 'blind_verdicts.jsonl'):
        path = OWN / name
        sealed = subprocess.check_output(['git', 'show', f'{SEAL}:{path.as_posix()}'])
        if sealed != path.read_bytes().replace(b'\r\n', b'\n'):
            raise ValueError(f'Sealed input changed: {path}')
    order = json.loads((OWN / 'blind_order.json').read_text())
    own = [json.loads(line) for line in (OWN / 'blind_verdicts.jsonl').read_text().splitlines()]
    with REF.open(newline='') as file:
        reference = list(csv.DictReader(file))
    ids = [r['crop'] for r in order['images']]
    refs = {r['blind_filename']: r for r in reference}
    if (len(ids) != 72 or len(set(ids)) != 72 or ids != [r['crop'] for r in own]
            or len(reference) != 72 or set(refs) != set(ids)):
        raise ValueError('Exactly the same 72 unique crops required in sealed order')
    inputs, pairs = [], []
    for position, (o, v) in enumerate(zip(order['images'], own), 1):
        # Resolve from this checkout, so a verifier can reproduce after landing.
        path = BASE / 'g273_detector_precision_blind_sample_artifact/blind_renders' / o['crop']
        m = manifest(path, o['resolution'])
        if m['sha256'] != o['sha256'] or m['bytes'] != o['bytes']:
            raise ValueError('Original crop changed')
        if not v['detail'].strip():
            raise ValueError('Every row requires free text')
        inputs.append(m)
        pairs.append(dict(crop=v['crop'], position=position, reference=refs[v['crop']]['category'],
                          second=v['category'], detail=v['detail'],
                          reference_detail=refs[v['crop']]['detail']))
    a, b = [r['reference'] for r in pairs], [r['second'] for r in pairs]
    result = agreement(a, b)
    result.update(sealing_sha=SEAL, reference_rater='G287 gpt-5.6-terra',
                  second_rater='G295 gpt-6-astra', machine=Path.cwd().as_posix(),
                  exposure=order['exposure'], mcnemar=paired_player(a, b),
                  labels=LABELS, disagreements=[r for r in pairs if r['reference'] != r['second']])
    for path in (REF, OWN / 'blind_order.json', OWN / 'blind_verdicts.jsonl'):
        inputs.append(manifest(path))
    for path in [BASE / 'specs/G295_spec.md', BASE / 'VERIFIER_CONTRACT.md',
                 BASE / 'RESULTS_LEDGER.md'] + [BASE / n for n in (
                     'g291_independent_second_rater_agreement_2026-09-04.md',
                     'g287_unconditioned_footpoint_content_2026-09-04.md',
                     'g288_describe_graphic_and_floor_crops_2026-09-04.md',
                     'g273_detector_precision_blind_sample_2026-09-04.md')]:
        inputs.append(manifest(path))
    for name, data in (('measurement_summary.json', result), ('paired_verdicts.json', pairs),
                       ('input_manifest.json', inputs)):
        (OWN / name).write_text(json.dumps(data, indent=2) + '\n', encoding='ascii')
    return result


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
