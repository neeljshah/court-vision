"""Local, read-only-input paired comparison of the sealed G291 crop judgments."""

import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Sequence

CATEGORIES = ('PLAYER', 'PERSON NOT PLAYER IN PLAY', 'NOT A PERSON', 'CANNOT JUDGE')
ALIASES = dict(zip(
    ('PLAYER on the court of play', 'PERSON not a player in play',
     'NOT A PERSON', 'CANNOT JUDGE'), CATEGORIES))
SEAL = 'b35967751945038273c8c65709e493322c386475'
BASE = Path('docs/evidence/tracking')
OWN = BASE / 'g291_independent_second_rater_agreement_artifact'
REF = BASE / 'g273_detector_precision_blind_sample_artifact'


def agreement(reference: Sequence[str], second: Sequence[str]) -> dict:
    """Compute four-class kappa and multinomial delta-method standard error."""
    if not reference or len(reference) != len(second):
        raise ValueError('Nonempty paired vectors of equal length required')
    matrix = [[0] * 4 for _ in range(4)]
    for a, b in zip(reference, second):
        matrix[CATEGORIES.index(a)][CATEGORIES.index(b)] += 1
    n = len(reference)
    rows = [sum(row) for row in matrix]
    cols = [sum(matrix[i][j] for i in range(4)) for j in range(4)]
    r, c = [v / n for v in rows], [v / n for v in cols]
    po = sum(matrix[i][i] for i in range(4)) / n
    pe = sum(x * y for x, y in zip(r, c))
    if pe == 1:
        raise ValueError('Kappa undefined for a single constant shared category')
    kappa = (po - pe) / (1 - pe)
    # Unconstrained gradient d kappa / d p_ij, contracted with
    # multinomial covariance (diag(p) - p p.T) / n.
    gradients = [
        (matrix[i][j] / n,
         ((i == j) * (1 - pe) - (1 - po) * (c[i] + r[j])) / (1 - pe) ** 2)
        for i in range(4) for j in range(4)
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
    """Exact two-sided McNemar test of paired PLAYER indicator judgments."""
    if len(reference) != len(second) or len(reference) < 2:
        raise ValueError('At least two equal-length paired observations required')
    lost = sum(a == 'PLAYER' and b != 'PLAYER' for a, b in zip(reference, second))
    gained = sum(a != 'PLAYER' and b == 'PLAYER' for a, b in zip(reference, second))
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
    """Validate sealed inputs, join every crop, and write additive evidence."""
    for name in ('blind_order.json', 'blind_verdicts.jsonl'):
        path = OWN / name
        sealed = subprocess.check_output(['git', 'show', f'{SEAL}:{path.as_posix()}'])
        # Git stores LF while this Windows checkout may use CRLF.
        if sealed != path.read_bytes().replace(b'\r\n', b'\n'):
            raise ValueError(f'Sealed input changed: {path}')
    order = json.loads((OWN / 'blind_order.json').read_text())['rows']
    own = [json.loads(line) for line in (OWN / 'blind_verdicts.jsonl').read_text().splitlines()]
    with (REF / 'blind_verdicts.csv').open(newline='') as file:
        ref = list(csv.DictReader(file))
    unblind = json.loads((REF / 'unblind_map.json').read_text())
    ids = [row['crop_id'] for row in order]
    if len(ids) != 72 or len(set(ids)) != 72 or ids != [r['crop_id'] for r in own]:
        raise ValueError('Require all 72 unique verdicts in sealed viewing order')
    refs = {f"blind_{int(r['blind_index']):03d}": r['verdict'] for r in ref}
    maps = {Path(r['render']).stem: r for r in unblind}
    if len(ref) != 72 or len(unblind) != 72 or set(refs) != set(ids) or set(maps) != set(ids):
        raise ValueError('Reference, map and sealed crop sets must match exactly')
    inputs, pairs = [], []
    for o, verdict in zip(order, own):
        source = manifest(Path(o['path']), o['resolution'])
        if source['sha256'] != o['sha256'] or source['bytes'] != o['bytes']:
            raise ValueError('Original crop identity changed')
        if not verdict['free_text'].strip():
            raise ValueError('Every verdict needs free text')
        inputs.append(source)
        crop_id = o['crop_id']
        pairs.append(dict(crop_id=crop_id, viewing_position=o['position'],
                          reference=refs[crop_id], second=ALIASES[verdict['category']],
                          free_text=verdict['free_text'], source_frame=maps[crop_id]['source_frame']))
    for path in (REF / 'blind_verdicts.csv', REF / 'unblind_map.json',
                 REF / 'blind_presentation_order.csv', OWN / 'blind_order.json',
                 OWN / 'blind_verdicts.jsonl'):
        inputs.append(manifest(path))
    reference, second = [r['reference'] for r in pairs], [r['second'] for r in pairs]
    summary = agreement(reference, second)
    summary.update(sealing_sha=SEAL, reference_rater='gpt-5.6-terra',
                   second_rater='gpt-6-astra', machine=str(Path.cwd()),
                   unique_source_frames=len({r['source_frame'] for r in pairs}),
                   mcnemar=paired_player(reference, second),
                   disagreements=[r for r in pairs if r['reference'] != r['second']])
    for name, data in (('measurement_summary.json', summary), ('paired_verdicts.json', pairs),
                       ('input_manifest.json', inputs)):
        (OWN / name).write_text(json.dumps(data, indent=2) + '\n', encoding='ascii')
    return summary


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
