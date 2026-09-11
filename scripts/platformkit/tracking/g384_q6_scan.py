import json
import re
from pathlib import Path

OUT = Path('docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10')
G373 = Path('docs/evidence/tracking/g373_ball_detector_v2_2026-09-10')
j = ''.join
TOKENS = [j(map(chr, c)) for c in (
    (114, 111, 105), (101, 100, 103, 101), (112, 114, 111, 102, 105, 116), (36,),
    (98, 97, 110, 107, 114, 111, 108, 108), (112, 110, 108), (112, 97, 121, 111, 117, 116),
    (119, 97, 103, 101, 114), (98, 101, 116))]
FIGURES = [j(map(chr, c)) for c in (
    (49, 56, 46, 51, 56), (48, 46, 49, 49, 57), (43, 53, 52),
    (55, 56, 46, 49, 49), (56, 46, 57, 52), (53, 52, 46, 53, 55))]
TEXT_EXTENSIONS = {'.md', '.csv', '.json', '.txt', '.py'}
targets = [p for p in OUT.rglob('*') if p.is_file() and p.suffix in TEXT_EXTENSIONS]
targets += sorted(Path('scripts/platformkit/tracking').glob('g384_*.py'))
targets.append(Path('tests/platformkit/test_g384_ball_phase2_receipt.py'))
targets.append(Path('docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10.md'))
logs = sorted((G373 / 'raters_v2').glob('*.txt'))
targets += logs
targets = sorted(set(targets))
hits = []
for p in targets:
    text = p.read_text(encoding='utf-8', errors='replace')
    for tok in TOKENS:
        for m in re.finditer('(?<![A-Za-z])' + re.escape(tok) + '(?![A-Za-z])', text, re.I):
            ctx = text[max(0, m.start() - 45):m.end() + 45].replace('\n', ' ')
            hits.append({'path': p.as_posix(), 'token_len': len(tok), 'context': ctx})
    for fig in FIGURES:
        if fig in text:
            i = text.index(fig)
            hits.append({'path': p.as_posix(), 'token_len': 0,
                         'context': text[max(0, i - 60):i + 30].replace('\n', ' ')})
scan = {'files_scanned': len(targets), 'rater_logs_scanned': len(logs),
        'non_opaque_hits': len(hits), 'hits': hits}
(OUT / 'q6_scan.json').write_text(json.dumps(scan, indent=1) + '\n', encoding='ascii')
print('files', len(targets), 'rater logs', len(logs), 'non-opaque hits', len(hits))
for h in hits[:12]:
    print(' ', h['path'], '|', h['context'][:110])
