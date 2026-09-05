"""Produce a worktree-local pod_run copy with the user-required fsync-only guard."""
from pathlib import Path


def main() -> None:
    """Keep shipping/fetching unchanged; remove blocking network-volume walks."""
    source = Path.home() / "bin/pod_run"
    content = source.read_text()
    start = content.index('$SSH "mkdir -p $R && dd')
    end = content.index("# ship code", start)
    content = content[:start] + '''$SSH "mkdir -p $R/g298_scratch && dd if=/dev/zero of=$R/g298_scratch/wrapper_fsync_probe.bin bs=1M count=8 conv=fsync" || { echo "POD FSYNC WRITE PROBE FAILED -- not running"; exit 3; }
echo "POD /workspace UNKNOWN; /workspace/wt UNKNOWN (MooseFS walk omitted; successful fsync is the disk gate)"

''' + content[end:]
    content = content.replace('WT="/c/Users/neelj/nba-track-$H"; [ -d "$WT" ] || WT="/c/Users/neelj/nba-ai-system"',
                              '[ "$H" = a6 ] || exit 2\nWT="/c/Users/neelj/nba-track-a6"\n[ -d "$WT" ] || exit 2')
    # Isolate this tiny route from the already-running bulk tar; never interrupt it.
    begin = content.index('( cd "$WT" && { find scripts')
    finish = content.index('\n$SSH "cd $R && ([ -e data ]', begin)
    content = content[:begin] + '''( cd "$WT" && printf '%s\\n' "${SHIP[@]}" | tar -cf - --transform='s,^,g298_code/,' -T - ) | $SSH "cd $R && tar -x --no-same-owner"
''' + content[finish:]
    target = Path("scripts/platformkit/tracking/g298_pod_run_minimal.sh")
    target.write_text(content, encoding="ascii", newline="\n")


if __name__ == "__main__":
    main()
