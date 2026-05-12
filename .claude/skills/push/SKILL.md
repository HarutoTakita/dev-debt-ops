---
name: push
description: 現在のブランチをリモートにプッシュし、プリプッシュフックの失敗を自動的に処理
---

ユーザー入力はエージェントから直接提供されるか、コマンド引数として提供される可能性があります - プロンプトを進める前に必ず考慮してください（空でない場合）。

ユーザー入力:

$ARGUMENTS

現在のブランチをリモートoriginにプッシュし、プリプッシュlefthookエラーを自動的に処理します。

## 実行手順

1. **現在のブランチを特定**:
   ```bash
   git branch --show-current
   ```

2. **プッシュされていないコミットをチェック**:
   ```bash
   git status
   git log origin/<branch>..HEAD --oneline 2>/dev/null || git log --oneline -5
   ```
   - プッシュするコミットがない場合、ユーザーに通知して停止。

3. **プッシュを試行**:
   ```bash
   git push origin <current-branch>
   ```
   - ブランチにまだupstreamがない場合、`git push -u origin <current-branch>`を使用。

4. **プッシュが成功した場合**: 成功を報告し、プッシュされたコミットを表示。

5. **プリプッシュフックが失敗した場合**: エラー出力を解析し、問題を修正:

   ### 一般的なプリプッシュフック失敗と修正:

   - **ruff-check (リントエラー)**: 適切なサービスディレクトリで`uv run ruff check --fix .`を実行、`uv run ruff check .`で検証
   - **ruff-format**: 適切なサービスディレクトリで`uv run ruff format .`を実行
   - **mypy (型エラー)**: 報告されたファイルを読み、型エラーを手動で修正
   - **pytest (テスト失敗)**: 失敗したテストを実行、エラーを読み、ソースコードまたはテストを修正
   - **prettier**: フロントエンドディレクトリで`npx prettier --write <files>`を実行
   - **eslint**: `npx eslint --fix <files>`を実行するか手動で修正
   - **svelte-check**: 報告されたファイルのTypeScript/Svelte型エラーを修正
   - **その他のフック失敗**: エラー出力を注意深く読み、適切な修正を適用

6. **フックエラー修正後**:
   - 修正ファイルをステージ: `git add <修正されたファイル>`（修正された特定のファイルのみステージ）
   - `/commit`スキル規約を使用して修正コミットを作成:
     ```bash
     git commit -m "$(cat <<'EOF'
     🐛 [fix] <hook名>のエラーを修正

     - <修正内容の詳細>

     🤖 Generated with [Claude Code](https://claude.ai/code)

     Co-Authored-By: Claude <noreply@anthropic.com>
     EOF
     )"
     ```
   - コミットメッセージは必ず`/commit`規約に従うこと:
     - フォーマット: `<emoji> [<type>] <説明>`
     - リント/フォーマット/型エラーの場合は通常`🐛 [fix]`、設定問題の場合は`🔨 [chore]`
     - **コミットメッセージは必ず日本語で作成すること**（絵文字プレフィックスと[type]タグは英語のまま）

7. **プッシュを再試行**: `git push origin <current-branch>`を再度実行。

8. **プッシュが再び失敗した場合**: ステップ5-7を**最大3回**繰り返す。3回試行後も失敗する場合、残りのエラーをユーザーに報告して停止。

9. **最終検証**: 結果を表示:
   ```bash
   git log origin/<branch>..HEAD --oneline 2>/dev/null || echo "All commits pushed."
   ```

## 重要な注意事項

- **ユーザーが明示的に要求しない限り`--force`や`--no-verify`は絶対に使用しない**
- **フックをスキップしない** — 常に根本的な問題を修正
- 修正コミットは可能な限り最小限にする — フックが報告したもののみ修正
- フック失敗が重要でないコードの変更を必要とする場合（論理バグによるテスト失敗など）、進行前にユーザーに尋ねる
- コミット前に特定のチェックをローカルで実行して修正が正しいことを常に検証
- ブランチがリモートから分岐している場合、ユーザーに通知し、どう進めるか尋ねる（強制プッシュしない）