# 変更履歴

すべての注目すべき変更はこのファイルに記録されます。

フォーマットは [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) に基づいています。

## [Unreleased]

### Added

- プロジェクト機能（issue-014）: Org 配下に第一級の Project（1 プロジェクト = 1 git リポジトリ）を導入。
  - バックエンド: `projects` テーブル + マイグレーション（org 内 slug 一意・1 リポジトリ 1 プロジェクトの部分ユニーク制約）、`/api/v1/orgs/{slug}/projects` の CRUD API、リポジトリアクセスの GitHub App 検証。
  - フロントエンド: サイドバー上部のプロジェクトスイッチャー（検索 + 最近開いた順）、プロジェクト作成フロー（RepoPicker 再利用）、プロジェクト設定（リネーム / 既定ブランチ / 削除）、Org ホーム（プロジェクト一覧）。

### Changed

- 機能メニュー（Galaxy / Matrix / Quizzes / Agents / Learning / Repos）を `/[org]/[project]/...` 配下へ再スコープし、プロジェクト単位に切り替わるようにした。パンくずを Org > Project > 機能に拡張。
