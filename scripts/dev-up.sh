#!/usr/bin/env bash
# デバッグ用: コンテナを起動しつつ、全サービスのログを起動直後から自動で docs/logs/ に素テキスト保存する。
#
# 使い方（リポジトリのどこからでも実行可）:
#   scripts/dev-up.sh            # `docker compose watch`（コード同期・既定の開発起動）＋ ログ自動保存
#   scripts/dev-up.sh up         # `docker compose up --build`（同期なし）＋ ログ自動保存
#
# - フォアグラウンドは通常どおり watch/up。ログ保存はバックグラウンドで自動的に走る。
# - Ctrl-C で watch/up を止めると、ログ追従も自動停止する（trap）。
# - 保存先: docs/logs/compose-<YYYYmmdd-HHMMSS>.log（stderr 込み・色除去・時刻付き）。
#   `*.log` は .gitignore 済みなのでコミットされない。
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p docs/logs
ts="$(date +%Y%m%d-%H%M%S)"
out="docs/logs/compose-${ts}.log"
mode="${1:-watch}"  # watch(既定) | up

# コンテナが1つでも現れるまで待ってから logs -f を張る（起動直後のビルド待ちに耐える）。
# `docker compose logs -f` は既存ログ→以後を流すので、起動時点からのログを取りこぼさない。
(
  until [[ -n "$(docker compose ps -q 2>/dev/null)" ]]; do sleep 1; done
  docker compose logs -f --no-color --timestamps
) >"$out" 2>&1 &
logpid=$!
# フォアグラウンド（watch/up）を抜けたらログ追従も止める。
trap 'kill "$logpid" 2>/dev/null || true' EXIT

echo "Container logs auto-saving -> ${out}" >&2
echo "（別ターミナルで  tail -f ${out}  で追えます / Ctrl-C で全体停止）" >&2

if [[ "$mode" == "up" ]]; then
  docker compose up --build
else
  docker compose watch
fi
