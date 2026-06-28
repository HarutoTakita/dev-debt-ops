# ProtoPedia 提出ドラフト — DevDebtOps

> Findy「DevOps × AI Agent Hackathon」提出用の下書き。ProtoPedia の各入力項目に対応。
> `※要記入` は本人が後で埋める箇所（動画・画像・メンバー等）。確定後に貼り付けて使う。

---

## 作品ステータス 〔必須〕

**開発中**（demo 可能な状態。登録後に「完成」へ変更可）

---

## 作品タイトル 〔必須〕

**DevDebtOps — 理解負債を“実測して返済”する Knowledge Debt Twin Agent**

> 別案: 「DevDebtOps：クイズで測る・エージェントで返す、理解負債のための DevOps プラットフォーム」

---

## 概要 〔必須〕

DevDebtOps は、ソフトウェア開発で見落とされがちな **「理解負債（Knowledge / Understanding Debt）」** —
“コードは動くが、誰もその中身を本当には理解していない” 状態 — を主役に据えたプラットフォームです。

従来の技術負債ツール（CodeScene 等）が **git blame からの「推測」** でコード負債を検知するのに対し、
DevDebtOps は **クイズで理解度を能動的に「実測」** します（blame 非依存。単独開発でも、コードを書かない PM でも計測可能）。
そのうえで **Google ADK で組んだ Twin Agent** が、知識負債と技術負債を横断的に自律判断し、
**学習プラン → クイズ再受験で返済する閉ループ** を駆動します。技術負債（コード負債）は廃止せず、
「どの理解ギャップが緊急か」を示す **ホットスポット（リスク信号）** として活用します。

「測る → どこが危ないか判断する → 学習/クイズ/返済 PR で返す → 再計測する」を AI エージェントが回す、
**理解負債のための DevOps** が DevDebtOps です。

---

## 画像 〔任意〕

`※要記入`（紹介画像は後日作成、最大5枚。例: Overview ダッシュボード / コード品質マップ / Knowledge Galaxy / クイズ画面 / Twin Agent の実行トレース）

---

## 動画 〔必須〕

`※要記入`（YouTube もしくは Vimeo の URL。デモ動画は後日作成）

---

## システム構成 〔必須〕

**システムアーキテクチャ図:** `docs/infra/infrastructure.drawio` をアップロード。

### 技術的補足

Google Cloud をフル活用したフルスタック・サーバーレス構成。

- **フロントエンド（SPA）** — SvelteKit 2（Svelte 5 runes）/ shadcn-svelte / Tailwind v4 / Paraglide（日本語・英語 i18n）。
  `adapter-static` の SPA としてビルドし、API コンテナに同梱して配信。
- **バックエンド（uv workspace モノレポ）** — `shared`（共有 enum / スキーマ / ORM `Job`）/ `api`（外部公開・FastAPI）/
  `service`（重い処理 worker・内部公開）の 3 メンバー構成。FastAPI + SQLModel + SQLAlchemy 2.0 async。
- **実行基盤** — **Cloud Run** に api（外部）と service（内部 worker）を別サービスとしてデプロイ。
  重い解析は **Cloud Tasks** 経由で service に非同期ディスパッチ（OIDC 認証）。`Job` ライフサイクルで状態管理・冪等化。
- **データ** — **Cloud SQL (PostgreSQL 17 + pgvector)**。本番は Private IP + 自動バックアップ + HA。
- **AI** — **Vertex AI 経由の Gemini**（ADC 認証、API キー不要）+ **Google ADK（Agent Development Kit）** で Twin Agent を構築。
- **セキュリティ／運用** — **Workload Identity Federation**（長期鍵を持たない CI 認証）/ Secret Manager /
  **Cloud Armor**（エッジでレート制限）/ Artifact Registry / Cloud Monitoring・Logging（5xx メトリクス・uptime チェック）。
- **IaC** — **Terraform**（`infra/gcp` 本体 + `infra/bootstrap/gcp`）。環境分離（staging / production）。

### AI エージェントの中核（“AI エージェントである必然性”）

解析の中核に **ADK Twin Agent** を置いています。コーディネータ（**PlanReActPlanner**）が、

1. **knowledge_debt_agent**（ファイル一覧取得 → 読込 → 理解ギャップ評価）
2. **code_debt_agent**（複雑度・重複・dead code 等のホットスポット）
3. **remediation_strategist**（返済戦略：クイズ / 学習ユニット / 返済 PR を所見ごとに判断）

を **AgentTool / LoopAgent** で自律的にオーケストレーションし、**どのホットスポットを・どこまで深掘りするか**を
自分で決め、十分と判断したら **自ら `exit_loop` を呼んで終了**します。**callbacks による予算ガード**（ツール/モデル/ファイル呼び出し上限）と
**plugin によるイベント永続化（`agent_trace`）** で、判断の根拠を後から追跡できます。
→ 固定手順では表せない「未知の探索空間・横断的リスク判断・適応的な深さ・能動測定の設計」を担うため、
**エージェントであることに必然性**があります。

### DevOps（“つくる。まわす。とどける。”）

- **CI**（GitHub Actions）— backend: ruff / ty / pytest、frontend: prettier / eslint / svelte-check / vitest。
- **CD** — `develop` push で staging 自動デプロイ、`v*.*.*` タグで production デプロイ（**承認ゲート付き**）。
  **Trivy** で CRITICAL/HIGH の CVE をブロック、リリースに **SBOM（CycloneDX）** を添付。
- **AI を DevOps に組み込み** — **Gemini による PR 自動レビュー**（Google 公式 `run-gemini-cli` を CI に統合。
  PR 作成時の自動レビュー + `@gemini-cli /review` コメント起動。WIF + 最小権限 SA で Vertex AI を呼ぶ）。
- **実運用への配慮** — WIF（鍵レス）、最小権限 SA の分離、Secret Manager、Cloud Armor、ヘルスチェック、
  環境分離、プリコミット（lefthook + gitleaks）。

---

## 開発素材（使用した開発ツール）〔必須〕

**Google Cloud**
- Cloud Run / Cloud SQL (PostgreSQL) / Cloud Tasks / Secret Manager / Cloud Armor / Artifact Registry /
  Cloud Monitoring・Logging / Workload Identity Federation
- **Vertex AI（Gemini）** / **Google ADK（Agent Development Kit）**

**フロントエンド**
- SvelteKit 2 / Svelte 5 / shadcn-svelte / Tailwind CSS v4 / Zod / Paraglide / bun / Vite

**バックエンド**
- Python 3.13 / FastAPI / SQLModel / SQLAlchemy 2.0 (async) / Alembic / fastapi-users / uv / pytest
- google-genai（Gemini SDK）/ google-adk

**インフラ・DevOps**
- Terraform / Docker / GitHub Actions / Trivy / gitleaks / lefthook
- Gemini PR レビュー（`google-github-actions/run-gemini-cli`）

**データベース**
- PostgreSQL 17（pgvector 拡張）

**開発支援**
- Claude Code（実装・レビュー支援）/ VS Code / gh CLI

---

## タグ 〔必須〕

`findy_hackathon`（必須）, `AIエージェント`, `ADK`, `Gemini`, `Vertex AI`, `Google Cloud`, `Cloud Run`,
`DevOps`, `理解負債`, `技術負債`, `ナレッジマネジメント`, `SvelteKit`, `FastAPI`, `Terraform`

---

## ストーリー 〔必須〕

### ① 本作品で解決したい課題とその背景

ソフトウェアは「動くこと」と「理解されていること」が別物です。コードは動くのに、
**その意図やリスクを誰も把握していない** 状態 —— これを私たちは **理解負債（Knowledge Debt）** と呼びます。
理解負債が溜まると、属人化・オンボーディングの遅延・レビューの形骸化・改修時の事故が増えます。

既存の技術負債ツールは、複雑度や `git blame` の履歴から **「おそらく危ない場所」を推測** できますが、
**「人が実際に理解しているか」は測れません**。さらに blame ベースの手法は、単独開発や
「コードを書かない PM」では成立しにくいという弱点があります。

DevDebtOps は、理解負債を **推測ではなくクイズで能動的に実測** し、AI エージェントが返済まで伴走することで、
この見えない負債を可視化・返済可能にします。

### ② 想定する利用ユーザー

- **テックリード / エンジニアリングマネージャー** — チームの理解度ホットスポットを把握し、レビューや学習の優先順位を決めたい
- **オンボーディング担当 / 新規参画メンバー** — どこから理解すべきかを学習ユニットとクイズで体系的に追いたい
- **属人化に悩むスタートアップ / 少人数チーム** — 「あの人しか分からない」を解消したい
- **コードを書かない PM・単独開発者** — blame ベースの手法では計測できない層でも、クイズで理解度を測りたい

### ③ プロダクトの特徴

1. **理解度を“実測”する（blame 非依存）** — クイズで能動的に計測。単独開発・非エンジニアでも測れる。
2. **AI エージェントが中核** — ADK の Twin Agent（コーディネータ + 知識/技術負債エージェント + 返済戦略家）が、
   ホットスポットの選定・深掘り深度・返済手段を **自律的に判断**。判断根拠は実行トレースに記録。
3. **返済の閉ループ** — 所見 → 学習プラン / 学習ユニット / 確認クイズ / 返済 PR を提案し、
   **クイズ再受験で返済を計測** する。測って終わりにしない。
4. **技術負債はリスク信号として活用** — 二軸マトリクスで「どの理解ギャップが緊急か」を示すホットスポットに位置づけ。
5. **AI を DevOps に統合した実運用志向** — Gemini による PR 自動レビューを CI に組み込み、
   WIF / Trivy / 承認ゲート / 環境分離など本番運用を意識した構成。

---

## メンバー登録 〔任意〕

`※要記入`

---

## 関連 URL 〔任意〕

- GitHub リポジトリ: `※要記入`（公開する場合）
- デモ環境（staging）: `※要記入`
- その他（スライド等）: `※要記入`

---

> 補足（提出前チェック）
> - 動画 URL（必須）・システムアーキテクチャ図（必須）の2点が揃えば必須項目は充足。
> - `infrastructure.drawio` は PNG/SVG にエクスポートして添付するとプレビューしやすい。
> - 紹介画像（任意）は5枚枠があるので、主要画面のスクショを用意すると訴求力が上がる。
