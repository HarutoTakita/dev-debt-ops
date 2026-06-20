# 認証強化: CSRF Origin 検証 / token_epoch・iat / OAuth メール検証

## 概要 / 重大度

**重大度: High（CSRF）+ Medium（壊れたログアウト無効化・OAuth 紐付け）。**

cookie ベース認証の防御の深さを補強し、`token_epoch` ログアウト無効化の機能不全を修正する。

## 該当箇所と問題

### A. CSRF 防御が access cookie の SameSite のみに依存（High）
- `backend/api/app/core/security.py:35-41` — access cookie は `SameSite=Lax`。
- `backend/api/app/main.py` — CORS/Origin ミドルウェアも CSRF トークンも無い。
- 状態変更系（`detect-debts` / `repayment-pr` / role PATCH 等）は `Lax` cookie のみで保護。
  refresh cookie は `Strict` + path 限定で良いが、変更系の大半が access cookie 側。
- **修正**: unsafe メソッド（POST/PATCH/PUT/DELETE）に対し `Origin`（無ければ `Referer`）を
  `FRONTEND_ORIGIN` allow-list と照合するミドルウェアを追加（fail-closed）。
  または double-submit CSRF トークン。CLAUDE.md のレート制限同様「エッジ前提」にせず明示する。

### B. `token_epoch` 無効化が常に存在しない `iat` を見ている（Medium・機能不全）
- `backend/api/app/core/access_token.py:33` — `int(data.get("iat", 0)) < token_epoch`。
  発行 JWT に `iat` が無いため常に `0`。結果、一度ログアウト（`auth_custom.py:160` で
  `token_epoch` を増分）すると以後そのユーザの access token は**恒久的に拒否**され、毎回 `/refresh`
  に落ちる（fail-secure だが制御が壊れている）。
- **修正**: トークン発行時に `iat` を付与（`write_token` をオーバーライド）、または login 時に
  `token_epoch` をリセット。logout→login→access のリグレッションテストを追加。

### C. OAuth 紐付けが未検証メールにフォールバックし得る（Medium）
- `backend/api/app/services/github_oauth_client.py:54-55` — primary+verified が無いとき
  `emails[0]`（未検証含む）にフォールバック。`auth.py:20` は `associate_by_email=True`。
  未検証メールが既存ローカルユーザと一致すると account takeover の余地。
- **修正**: 未検証メールにフォールバックしない。メール不在時に既に使う
  `{id}+{login}@users.noreply.github.com` 合成形を優先。

### D. access JWT が汎用 audience・issuer 無し（Medium・防御の深さ）
- `backend/api/app/core/security.py:44-49` — `token_audience`/`iss` 未設定で
  ライブラリ既定 `fastapi-users:auth`。同一 `SECRET_KEY` が他用途トークンも署名。
- **修正**: アプリ固有 audience（例 `rosetta:access`）と `iss` を設定。

## 受け入れ条件

- A: 許可外 Origin の変更系リクエストが 403（テスト）。許可 Origin/同一サイトは通過。
- B: logout 後に login すると新 access token が受理される（テスト）。
- C: 未検証メールでの自動紐付けが起きない（テスト）。
- backend gates 緑。フロントの既存ログイン/リフレッシュ動線が壊れないこと（必要なら fetch に
  `credentials`/headers 調整）。

## 対象外

- レート制限（Cloud Armor、エッジ）。
