#!/usr/bin/env bash
# Extract release notes for a given version from CHANGELOG.md
set -euo pipefail

VERSION="${1:?Usage: extract-changelog.sh <version>}"
VERSION="${VERSION#v}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHANGELOG="$ROOT/CHANGELOG.md"

# Extract section between ## [VERSION] and the next ## [ or reference links, trimming trailing blanks
NOTES=$(awk -v ver="$VERSION" '
  /^## \[/ {
    if (found) exit
    if ($0 ~ "\\[" ver "\\]") { found=1; next }
  }
  found && /^\[.*\]:/ { exit }
  found { buf = buf $0 "\n" }
  END {
    # trim trailing blank lines
    sub(/\n+$/, "\n", buf)
    printf "%s", buf
  }
' "$CHANGELOG")

if [ -z "$NOTES" ]; then
  echo "Error: No changelog entry found for version $VERSION" >&2
  exit 1
fi

printf '%s\n' "$NOTES"
