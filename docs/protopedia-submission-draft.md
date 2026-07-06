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

「コードは動くが、誰も中身を本当には理解していない」— この**理解負債（Knowledge Debt）を実測して返済する**AI エージェント・プラットフォームです。git blame からの推測ではなくクイズで理解度を能動的に測り、Google ADK の Twin Agent が学習プラン・確認クイズ・修正 PR を提案。クイズの再受験で“返済できたか”まで見届けます。

---

## 画像 〔任意〕

`※要記入`（紹介画像は後日作成、最大5枚。例: Overview ダッシュボード / コード品質マップ / Knowledge Galaxy / クイズ画面 / Twin Agent の実行トレース）

---

## 動画 〔必須〕

`※要記入`（YouTube もしくは Vimeo の URL。デモ動画は後日作成）

動画の構成を考える
1. 課題とその背景、想定する利用ユーザーについて簡単に共有
2. アプリのデモ動画を見せながら何ができるのかを見せる
  - ダッシュボードの説明
  - 理解度マップの説明
  - クイズと学習の説明
  - コード品質マップの作成
  - コード改善の説明
  - 
3. どのように実装しているかの仕組みを共有する

  #### 3-1. リポジトリ解析の Agentic パイプライン（メインで説明）

  全体像：Cloud Tasks から内部 Cloud Run の worker（service）が 1 つの Job として起動し、
  **「探索 → 確定」の 2 段エージェント（ADK / Gemini）** と **決定的な解析バックボーン** を組み合わせた
  ハイブリッド構成で解析する。LLM に「探索・意味づけ」を任せ、計測・検知は決定的ツールで再現性を担保する設計。

  - **① GitHub リポジトリをアプリ内に取り込む**
    - **GitHub App の installation token**（Secret Manager の秘密鍵から RS256 JWT で都度発行）で認証。
    - 対象ブランチを **`git clone --depth 1 --single-branch`（浅いクローン）** で一時ディレクトリに取得。
      → Serena(LSP) や CodeGraphContext が **ディスク上の実プロジェクトツリー** を必要とするため。
    - トークンは URL に埋めず `http.extraHeader` で渡し、on-disk の git 設定に残さない。
      clone できない場合は **GitHub REST API にフォールバック**（graceful degradation）。処理後は一時ディレクトリを削除。

  - **② ADK エージェントによる自律探索（探索 → 確定の 2 段）**
    - `analysis_explorer`（LlmAgent）が repo ツール＋MCP で **コード構造・履歴・ホットスポットを自律的に探索** し所見を作成。
    - `base_author`（LlmAgent）がその所見を **構造化スキーマ**（機能・コード所見・理解所見・技術スタック）に確定。
    - モデルは **Vertex AI 経由の Gemini（ADC 認証・API キー不要）**。
    - **予算ガード**（ツール/モデル/ファイル呼び出しの上限を callbacks で強制）と、
      **全イベントのトレース永続化**（判断根拠を Job に記録）で、暴走やコスト膨張を抑えつつ挙動を追跡可能に。

  - **③ MCP を使用（3 サーバーを stdio サブプロセスで起動し、ADK の McpToolset で接続）**
    - **Serena（LSP）**：シンボルの定義・参照・実装を辿る **意味的コードナビ**（ミクロな理解）。
    - **CodeGraphContext**：呼び出し連鎖・モジュール依存・影響範囲・dead code・複雑度（**マクロな構造把握**。埋め込み KuzuDB）。
    - **GitHub MCP（read-only）**：PR/レビュー履歴・著者の偏り・セキュリティアラート（**プロセス軸**）。
    - ※ Semgrep / Trivy は MCP ではなく **決定的な CLI 解析** として別途実行（再現性・確定的な検知結果のため）。
    - → ミクロ（LSP）× マクロ（グラフ）× プロセス（GitHub）の 3 視点を横断して探索できるのがエージェントの強み。

  - **④ 決定的な解析バックボーン**
    - 機能クラスタリング → コード品質検知（重複・複雑度・dead code・Trivy/Semgrep）→ 理解負債検知 →
      学習プラン・クイズ生成 を順に実行し、結果を DB に upsert。エージェントの定性所見と決定的な計測を重ねて精度を確保。

  - **⑤ シークレット・個人情報（PII）のマスキング**
    - **保護対象は「LLM（Gemini）へ渡す直前のプロンプト全文」**（外部モデルへ機密を送らないための多層防御）。
    - **シークレット**：正規表現（各種 API キー・トークン・PEM 秘密鍵 等）＋ **detect-secrets（エントロピー検知）** の 2 層で常時マスキング。
    - **PII**：標準は正規表現（メール・電話・クレカ・IP 等）でマスキング。さらに **Google Cloud DLP（Sensitive Data Protection）**
      に切り替え可能（infra で API 有効化・SA 権限付与済み。infoType 単位で匿名化。DLP 失敗時は正規表現へ自動フォールバック）。

  #### 3-2. インフラ構成

  - **Cloud Run ＋ タスクキューによるスケーラブルな構成**
    - **api（外部公開）** と **service（内部専用・重い解析 worker）** を **Cloud Run の別サービス** に分離。
    - 重い解析は **Cloud Tasks**（キュー `job-requests`）経由で **非同期ディスパッチ**。api は **OIDC トークン**で service を認証、
      **リトライ（最大 5 回・指数バックオフ）** で信頼性を確保。負荷に応じて自動スケール（api 0–5 / service 0–10 インスタンス）。
    - service は解析向けに CPU/メモリ・タイムアウトを厚く（例：2 vCPU / 2 GiB / 30 分）確保。

  - **Cloud Armor・Google DLP によるセキュリティ**
    - **Cloud Armor**：外部 HTTPS ロードバランサのエッジで **レート制限**（ログイン 5/min・リフレッシュ 30/min 等、超過は `429`）。
    - **Google Cloud DLP**：機密データ匿名化を組み込み（有効化可能。上記 3-1 ⑤）。
    - 併せて **Secret Manager**（平文の環境変数を持たない）、**Workload Identity Federation**（CI は長期鍵レス）、
      **VPC ＋ Serverless VPC Access**、本番 Cloud SQL は **Private IP**、最小権限 SA の分離で多層防御。
4. 実運用に向けた取り組み
    - 


（4. 開発の進め方）
  - GitHub Actions で Terraform Deploy
  - PR に対して、静的解析に加え、Gemini によるレビューを行い、質の高い開発ループを心がけた

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
- i18n（国際化）まで考慮
### AI エージェントの中核（“AI エージェントである必然性”）

解析の中核に、**オーケストレーターエージェント × サブエージェント × hooks** を組み合わせた **Agentic アーキテクチャ**（Google ADK）を据えています。

- **オーケストレーター × サブエージェント** — ワークフロー型の **オーケストレーターエージェント（ADK `SequentialAgent`）** が、
  役割の異なる **サブエージェント** を協調させて解析を進めます。
  1. **探索サブエージェント（`analysis_explorer`）** — repo ツールと MCP を使い、コード構造・依存・履歴・ホットスポットを
     **自律的に探索**（どのファイルを・どこまで深掘りするかをエージェント自身が判断）。
  2. **確定サブエージェント（`base_author`）** — 探索の所見を構造化スキーマ（機能 / コード所見 / 理解所見 / 技術スタック）に確定。
  - さらに解析パイプライン全体が上位のオーケストレーターとして、**用途特化のサブエージェント**（学習プラン生成 / 確認クイズ生成 /
    コードウォークスルー / 返済 PR 提案 / 技術スタック抽出 / 機能クラスタリング）と **決定的な解析ツール** を束ねて実行します。
- **hooks（callbacks / plugins）** — ADK の **before/after callbacks** を hooks として差し込み、**予算ガード**（ツール・モデル・
  ファイル呼び出しの上限）や巨大なツール結果の切り詰めを強制。**plugin** で全イベントを **トレースとして永続化**（判断根拠を後から追跡）し、
  さらに **before-model hook で LLM 送信前のシークレット / PII をマスキング** します。
- **ツール（MCP × 決定的解析）** — サブエージェントは **MCP（Serena=LSP / CodeGraphContext=依存グラフ / GitHub=履歴・レビュー）**
  で micro・macro・process の 3 視点を横断しつつ、**Semgrep / Trivy 等の決定的 CLI 解析** を組み合わせ、計測・検知の再現性を担保します。

→ 固定手順では表せない「未知の探索空間・横断的リスク判断・適応的な深さ・能動測定の設計」を、
**オーケストレーター＋サブエージェント＋hooks** で担うため、**エージェントであることに必然性**があります。

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
- Python 3.13 / FastAPI / SQLModel / SQLAlchemy 2.0 (async) / Alembic / uv / pytest
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

`findy_hackathon`（必須）, `AIエージェント`, `ADK`, `Vertex AI`, `Google Cloud`, `Cloud Run`,
`DevOps`, `理解負債`, `技術負債`, `SvelteKit`, `FastAPI`, `Terraform`

---

## ストーリー 〔必須〕

### ① 本作品で解決したい課題とその背景

【AI時代に急速に蓄積する「理解負債」】

Claude Code や Codex、Gemini CLI をはじめとするAIコーディングツールの普及により、DevOpsにおける「開発」と「運用」のサイクルがかつてないほど加速しています。
しかし今、ソフトウェア開発の本質を揺るがす深刻な問題が浮き彫りになっています。

それが「理解負債」です。

理解負債とは、従来の技術負債のように「設計の甘さを自覚している状態」とは異なり、「AIが生成したコードが何をしているのか、なぜ動いているのか、なぜそう書かれているのかを説明できない状態」を指します。

理解負債が発生してしまう原因として、人間はAIが出力した「もっともらしいコード」を無意識に信頼してしまうことが指摘されています。
実際にAnthropic社が発表したエンジニアのスキル形成に関する研究では、AIの支援を受けた開発者は自力で書いたグループに比べて「コード理解度テスト」のスコアが17%低いという結果が出ました。
コードは期日通りにデプロイされる一方で、開発者の「理解」だけが置き去りにされていることが実証されています。

こうしたAIへの過信と、実装過程における思考のスキップも相まって、理解負債が現代のソフトウェア開発において急速に蓄積しています。

【既存ツールの限界と本プロダクトの強み】

ソフトウェアは「動くこと」と「理解されていること」が別物です。
既存の技術負債検知ソリューションは、コードの複雑度や参照関係から「おそらく危ない場所」を推測することはできても、「人が実際にそのコードを理解しているか」は測れません。
コードは動くのに、その意図やリスクを誰も把握していない。
この「理解負債」を放置すれば、属人化・オンボーディングの遅延・レビューの形骸化・改修時の工数などが増大します。

DevDebtOpsは、既存ツールがアプローチできていない理解負債を、AIエージェントがリポジトリ解析を通して作成した学習プランとクイズで能動的に実測し、
AIエージェントが「返済まで伴走する」ことで解決します。
加速し続けるDevOpsのサイクルの中に、AIエージェントを通じて「人間の確かな理解」を取り戻し、見えない理解負債を可視化・返済可能にする全く新しいアプローチです。

### ② 想定する利用ユーザー

- **テックリード / マネージャー** — チームメンバーの理解度が低い箇所を把握し、レビューや学習の優先順位を決めたい
- **オンボーディング担当 / 新規参画メンバー** — どこから理解すべきかを学習ユニットとクイズで体系的に追いたい

### ③ プロダクトの特徴

1. **コア機能① AI エージェントによる高度なリポジトリ解析** — ADK で構築したオーケストレーター＋サブエージェントが、MCP（Serena / CodeGraphContext / GitHub）と静的解析（Semgrep / Trivy 等）を使いながらリポジトリを探索し、機能ごとの学習プランとクイズの生成、品質の低いソースコードの検知と修正計画の生成などを行う。
2. **コア機能② グラフビューによる理解負債の可視化・クイズと学習による改善** - ソースコードを機能単位でクラスタリングし、機能ごとに学習プランと理解度確認テストを生成
3. **コア機能③ 品質の低いコードに対する推奨事項提案と自動修正** - 解析で検出した低品質のコードに対して、推奨事項を GitHub Issue として作成し、自動修正の PR 作成まで行える
4. **実運用を見据えた機能** — GitHub SSO を用いた認証・認可機能、プロジェクト管理機能、オンボーディングガイド、充実したショートカット、管理者によるユーザー管理機能、課金を伴う機能を管理者によるクレジット付与で制御、i18nを考慮した多言語翻訳、リリースバージョンの履歴確認機能など

---

## メンバー登録 〔任意〕

`※要記入`

---

## 関連 URL 〔任意〕

- GitHub リポジトリ: `https://github.com/HarutoTakita/dev-debt-ops`
- デモ環境（staging）: `※要記入`
- その他（スライド等）: `※要記入`
