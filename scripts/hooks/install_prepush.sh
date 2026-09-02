#!/bin/sh
# Install the S28 pre-push guard into this repo's .git/hooks. Idempotent.
# Usage: sh scripts/hooks/install_prepush.sh
set -e
root=$(git rev-parse --show-toplevel)
cd "$root"
dir="$(git rev-parse --git-dir)/hooks"
mkdir -p "$dir"
cat > "$dir/pre-push" <<'HOOK'
#!/bin/sh
# Installed by scripts/hooks/install_prepush.sh (harness row S28).
# Evidence: docs/evidence/harness/S28_prepush_guard_2026-09-03.md
exec python scripts/hooks/prepush_guard.py "$@"
HOOK
chmod +x "$dir/pre-push"
echo "installed: $dir/pre-push"
