#!/bin/bash
# Recompile requirements.txt and requirements-ci.txt under the cooldown:
# nothing published in the last 7 days is eligible. CI installs both files
# with hash checking, so recompile the two together, never just one.
#
# Usage: ./compile_requirements.sh [pip-compile args]
#   (none)          re-lock after editing a .in file; pins older than the cutoff stay
#   -P pkg[==ver]   upgrade one package and whatever it requires
#   -U              upgrade everything to the newest eligible version
# CUTOFF=2026-10-21T00:00:00Z overrides the default of 7 days ago. A pin newer
# than the cutoff is downgraded on every run; changed pins are listed at the end.
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v pip-compile >/dev/null && [ -x ./venv/bin/pip-compile ]; then
  PATH="$PWD/venv/bin:$PATH"
fi
want=$(sed -n 's/^pip-tools==\([^ \\]*\).*/\1/p' requirements.txt)
have=$(pip-compile --version 2>/dev/null | sed 's/.*version //') || true
if [ "$have" != "$want" ]; then
  echo "need pip-compile $want as pinned in requirements.txt, found ${have:-none}" >&2
  exit 1
fi

cutoff=${CUTOFF:-$(python3 -c 'from datetime import *
print((datetime.now(timezone.utc) - timedelta(7)).strftime("%Y-%m-%dT00:00:00Z"))')}
echo "Cutoff: $cutoff"

# Compile in a scratch copy so a failure in the second file leaves both untouched.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp requirements.in requirements-ci.in requirements.txt requirements-ci.txt "$tmp"
# --allow-unsafe pins pip and setuptools too: nothing installs without a hash.
# --strip-extras keeps the locks usable as pip constraints files.
for f in requirements.in requirements-ci.in; do
  (cd "$tmp" && pip-compile --generate-hashes --allow-unsafe --strip-extras \
    --pip-args "--uploaded-prior-to $cutoff" "$@" "$f")
done

for f in requirements.txt requirements-ci.txt; do
  diff <(grep -E '^[A-Za-z0-9_.-]+==' "$f") <(grep -E '^[A-Za-z0-9_.-]+==' "$tmp/$f") \
    | sed -n "s/ \\\\$//; s|^[<>] |$f: &|p" || true
  cp "$tmp/$f" .
done
