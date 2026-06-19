# 変更履歴

すべての注目すべき変更はこのファイルに記録されます。

フォーマットは [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) に基づいています。

## [Unreleased]

### Added

- 非同期タスク基盤（issue-016）: api→service の Cloud Tasks ディスパッチ + Job ライフサイクルを実装。
  - shared: `Job` モデルを軽量化（enum は String 永続化）、`TaskDispatcher` / `BlobClient` Protocol、`echo` / `ping` パイプライン + レジストリ + `run_task`（冪等な DB 直書き）、camelCase 共通スキーマ、`MockBlobClient` / `parse_gcs_url`。
  - api: `CloudTasksDispatcher`（OIDC 付き）/ `MockTaskDispatcher`、`GcsBlobClient`、`enqueue_job`（GCS スピルオーバー）、`timeout_stale_jobs`、in-process mock-worker（lifespan 起動）、`GET /api/v1/jobs/{id}`、`jobs` テーブルのマイグレーション（0005）。
  - service: `POST /tasks/{pipeline}`（Cloud Tasks HTTP ターゲット）— OIDC 検証 / `$requestRef` 解決 / 冪等処理 / Cloud SQL への結果直書き（2xx ack・5xx リトライ）。
  - 結果通知は Pub/Sub を使わず service が Cloud SQL に直書きし、フロントは `GET /jobs/{id}` をポーリングする。ローカルは GCP 不要（全 mock）で end-to-end が回る。
- プロジェクト機能（issue-014）: Org 配下に第一級の Project（1 プロジェクト = 1 git リポジトリ）を導入。
  - バックエンド: `projects` テーブル + マイグレーション（org 内 slug 一意・1 リポジトリ 1 プロジェクトの部分ユニーク制約）、`/api/v1/orgs/{slug}/projects` の CRUD API、リポジトリアクセスの GitHub App 検証。
  - フロントエンド: サイドバー上部のプロジェクトスイッチャー（検索 + 最近開いた順）、プロジェクト作成フロー（RepoPicker 再利用）、プロジェクト設定（リネーム / 既定ブランチ / 削除）、Org ホーム（プロジェクト一覧）。

### Changed

- 機能メニュー（Galaxy / Matrix / Quizzes / Agents / Learning / Repos）を `/[org]/[project]/...` 配下へ再スコープし、プロジェクト単位に切り替わるようにした。パンくずを Org > Project > 機能に拡張。
