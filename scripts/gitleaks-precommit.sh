#!/usr/bin/env bash
# Pre-commit secret scan, referenced by lefthook.yml (`pre-commit.commands.gitleaks`).
#
# Scans ONLY the staged diff with gitleaks (fast even on large commits). Tries to
# auto-install the binary on first run (Homebrew on macOS, `go install` on Linux). If
# gitleaks is unavailable and cannot be installed, it warns and passes rather than blocking
# commits — secret scanning still runs in CI. When gitleaks IS present, a finding fails the
# commit (non-zero exit) so secrets never get committed.
set -euo pipefail

_have() { command -v "$1" >/dev/null 2>&1; }

_install_gitleaks() {
  if _have brew; then
    brew install gitleaks >/dev/null 2>&1 && return 0
  fi
  if _have go; then
    GOBIN="${GOBIN:-$HOME/go/bin}" go install github.com/gitleaks/gitleaks/v8@latest >/dev/null 2>&1 && return 0
  fi
  return 1
}

BIN="$(command -v gitleaks 2>/dev/null || true)"
if [ -z "$BIN" ] && _install_gitleaks; then
  BIN="$(command -v gitleaks 2>/dev/null || true)"
  [ -z "$BIN" ] && [ -x "$HOME/go/bin/gitleaks" ] && BIN="$HOME/go/bin/gitleaks"
fi

if [ -z "$BIN" ] || ! [ -x "$BIN" ]; then
  echo "⚠️  gitleaks 未インストールのため pre-commit の秘密スキャンをスキップしました。" >&2
  echo "    導入: brew install gitleaks  /  go install github.com/gitleaks/gitleaks/v8@latest" >&2
  echo "    （秘密検知は CI でも実行されます）" >&2
  exit 0
fi

# Scan staged changes only; redact any detected secret values from the output.
exec "$BIN" protect --staged --redact --verbose
