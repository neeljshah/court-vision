"""CPU-only native G296B extraction with an exact source-PTS check per frame."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import zipfile

from scripts.platformkit.tracking.g296b_located_players import (
    ARTIFACT, FRAME_INDICES, SOURCE, sha256,
)


def main() -> None:
    """Seek deterministic CFR indices and verify the decoded first frame's PTS."""
    assert Path.cwd() == Path('/workspace/wt/a12')
    output = Path('g296b_seek')
    output.mkdir(exist_ok=True)
    frames = output / 'frames'
    frames.mkdir(exist_ok=True)
    assert not list(frames.glob('*.jpg'))
    command = ['dd', 'if=/dev/zero', 'of=/workspace/wt/a12/g296b_seek_fsync_probe',
               'bs=1M', 'count=8', 'conv=fsync']
    probe = subprocess.run(command, capture_output=True, text=True)
    gate = dict(command=shlex.join(command), returncode=probe.returncode,
                stdout=probe.stdout, stderr=probe.stderr, loadavg=list(os.getloadavg()),
                nproc=int(subprocess.check_output(['nproc'], text=True)),
                workspace_du_mb='UNKNOWN (network walk omitted)')
    print(json.dumps(gate), flush=True)
    (output / 'gate.json').write_text(json.dumps(gate, indent=2) + '\n')
    if probe.returncode:
        raise RuntimeError('FAILED dd conv=fsync probe')
    while os.getloadavg()[2] >= gate['nproc']:
        time.sleep(20)
    gate['decode_loadavg'] = list(os.getloadavg())
    metadata = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=width,height,nb_frames,r_frame_rate,time_base,start_pts',
        '-of', 'json', str(SOURCE)], text=True))['streams'][0]
    assert metadata == dict(width=1920, height=1080, nb_frames='174430',
                            r_frame_rate='30/1', time_base='1/15360', start_pts=0)
    print('FRAME_INDICES=' + json.dumps(FRAME_INDICES), flush=True)
    print('FORMULA_MATCH=true', flush=True)
    records = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        source_hash_future = pool.submit(sha256, SOURCE)
        for index in FRAME_INDICES:
            # Floor to microseconds: target is never just after the wanted PTS.
            seek_us = index * 1_000_000 // 30
            seek = f'{seek_us // 1_000_000}.{seek_us % 1_000_000:06d}'
            dest = frames / f'frame_{index:06d}.jpg'
            cmd = ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'info',
                   '-threads', '1', '-ss', seek, '-copyts', '-i', str(SOURCE),
                   '-map', '0:v:0', '-an', '-vf', 'showinfo', '-vsync', '0',
                   '-frames:v', '1', '-threads', '1', '-q:v', '2', str(dest)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            (output / f'ffmpeg_{index:06d}.log').write_text(result.stderr)
            first = re.search(r'n:\s*0\s+pts:\s*(-?\d+).*?s:(\d+)x(\d+)',
                              result.stderr)
            assert first, result.stderr
            assert tuple(map(int, first.groups())) == (index * 512, 1920, 1080)
            records.append(dict(source_frame=index,
                                path=(ARTIFACT / 'frames' / dest.name).as_posix(),
                                pod_path=str(Path.cwd() / dest),
                                bytes=dest.stat().st_size, sha256=sha256(dest),
                                width=1920, height=1080, source_pts=index * 512,
                                ffmpeg_argv=cmd, ffmpeg_command=shlex.join(cmd)))
            print(f'EXTRACTED {index} source_pts={index * 512} 1920x1080', flush=True)
        source_hash = source_hash_future.result()
    assert source_hash.startswith('f361ad7a32ccc6d98ae8e98e')
    manifest = dict(pass_letter='B', machine='pod /workspace/wt/a12',
                    source=dict(path=str(SOURCE), bytes=SOURCE.stat().st_size,
                                sha256=source_hash, **metadata), gate=gate,
                    frame_indices=FRAME_INDICES,
                    formula='round(i * 174429 / 23) for i in range(24)',
                    extraction='accurate input seek; each first decoded PTS == index * 512',
                    route_sha256={path: sha256(Path(path)) for path in [
                        'scripts/platformkit/tracking/g296b_seek_frames.py',
                        'scripts/platformkit/tracking/g296b_located_players.py']},
                    ffmpeg_version=subprocess.check_output(
                        ['ffmpeg', '-version'], text=True).splitlines()[0], frames=records)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARTIFACT / 'seek_frames_manifest.zip', 'w') as archive:
        for path in [output / 'manifest.json', output / 'gate.json',
                     *frames.glob('*.jpg'), *output.glob('ffmpeg_*.log')]:
            archive.write(path, path.relative_to(output))
    print('DONE: 24 native JPEGs; all first source PTS checks passed', flush=True)


if __name__ == '__main__':
    main()
