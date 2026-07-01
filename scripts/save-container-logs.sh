#!/usr/bin/env bash
# デバッグ用: docker compose のコンテナログをそのまま docs/logs/ にテキスト保存する。
#
# 使い方（リポジトリのどこからでも実行可）:
#   scripts/save-container-logs.sh              # 全サービスの現在ログをスナップショット保存
#   scripts/save-container-logs.sh -f           # 全サービスを追従(-f)し、Ctrl-C まで書き続ける
#   scripts/save-container-logs.sh service      # 特定サービス(api/service/db)のみスナップショット
#   scripts/save-container-logs.sh -f service   # 特定サービスを追従
#
# 出力先: docs/logs/compose[-<service>]-<YYYYmmdd-HHMMSS>.log
# ※ docs/logs/*.log は .gitignore の `*.log` で追跡対象外（コミットされない）。
set -euo pipefail

# リポジトリルート（このスクリプトの1つ上）へ移動して compose.yml を確実に見つける。
cd "$(dirname "$0")/.."

follow=""
if [[ "${1:-}" == "-f" || "${1:-}" == "--follow" ]]; then
  follow="--follow"
  shift
fi
service="${1:-}"  # 省略時は全サービス

mkdir -p docs/logs
ts="$(date +%Y%m%d-%H%M%S)"
name="compose"
[[ -n "$service" ]] && name="compose-${service}"
out="docs/logs/${name}-${ts}.log"

echo "Saving container logs -> ${out}${follow:+ (following; Ctrl-C to stop)}" >&2

# --no-color: 端末エスケープを除去した素のテキスト。--timestamps: 各行に時刻を付与（デバッグ向き）。
# stderr も取り込む（2>&1）。follow 時はプロセスが続くのでそのまま追記され続ける。
docker compose logs --no-color --timestamps ${follow} ${service:+"$service"} >"$out" 2>&1
