# service の `/tasks/{pipeline}` OIDC 検証を fail-closed にする

## 概要 / 重大度

**重大度: Critical（認可バイパス）。**

service（内部 Cloud Run、Cloud Tasks の HTTP ターゲット）の `POST /tasks/{pipeline}` は
パイプラインを実行し Job 行・ドメイン行を Cloud SQL に直接書き込む唯一の入口である
（返済 PR パイプラインの GitHub 書き込みを含む）。この入口の OIDC 検証が、設定の
**デフォルト値次第で無効化される（fail-open）**。

## 該当箇所

- `backend/service/service/dependencies.py:21-22` — `verify_oidc` は `use_mock_queue()` が真の間、
  認証チェックを早期 return でスキップする。
- `backend/service/service/config.py:13` — `USE_MOCK_QUEUE` は
  `os.environ.get("USE_MOCK_QUEUE", "true")` で **デフォルト `true`**。
- 対照として `backend/api/app/core/config.py`（`_validate_production_settings`）は本番で危険設定を
  強制的に弾くバリデータを持つが、service 側には**同等のガードが無い**。

## 問題

内部 service を `USE_MOCK_QUEUE=false` を明示せずにデプロイすると、`POST /tasks/{pipeline}` は
OIDC 検証なしで到達可能になる。ネットワーク的に到達できる任意の主体が、`installation_id` /
`owner` / `repo` / `debt_id` を偽造して任意パイプラインを起動でき、Job 行の書き込みや
GitHub 書き込み（返済 PR）まで誘発し得る。デフォルトが「安全でない側」に倒れている点が問題。

## 修正方針

1. **fail-closed 化**: `USE_MOCK_QUEUE` のデフォルトを `false` にする。dev（docker compose）は
   `.env.dev` / compose 環境変数で明示的に `true` を渡す（`.env.example` を更新）。
2. **本番ガード**: service の `config.py` に api と同等のバリデータを追加し、prod/GCP 環境
   （`ENVIRONMENT` が dev 以外）では `USE_MOCK_QUEUE=true` を起動時エラーにする。
3. `verify_oidc` のスキップ分岐に「dev のみ」であることを示すログ/コメントを残す。

## 受け入れ条件

- `USE_MOCK_QUEUE` 未設定時、service 起動時または最初のリクエストで OIDC 検証が有効。
- prod 環境で `USE_MOCK_QUEUE=true` を与えると起動が失敗する（テスト）。
- 既存の dev フロー（`docker compose watch` + mock queue）は `.env.dev` 設定で従来通り動作。
- `cd backend && uv run --directory service pytest` 緑、ruff/ty 緑。

## 対象外

- OIDC の audience/issuer 検証強化（必要なら別 issue）。
