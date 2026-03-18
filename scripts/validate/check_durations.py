import subprocess, os

clips = {}
for f in os.listdir('data/videos'):
    if f.endswith('.mp4'):
        r = subprocess.run(['ffprobe','-v','quiet','-show_entries',
            'format=duration','-of','csv=p=0', f'data/videos/{f}'],
            capture_output=True, text=True)
        try:
            dur = float(r.stdout.strip())
        except ValueError:
            dur = 0
        clips[f] = dur
        print(f'{f}: {dur:.0f}s ({dur/60:.1f}min)')

if clips:
    longest = max(clips, key=clips.get)
    print(f'\nLONGEST: {longest} = {clips[longest]/3600:.2f}h ({clips[longest]:.0f}s)')
    long_clips = [(k,v) for k,v in clips.items() if v > 3600]
    print(f'Clips >= 60min: {long_clips}')
