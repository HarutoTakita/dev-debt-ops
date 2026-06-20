# ユースケース図

Rosetta（Tech Debt Twin Agent）のアクターと主要ユースケースを Mermaid で示す。
Mermaid に UML ユースケース図の専用記法は無いため、**アクター → ユースケース（システム境界）** を
flowchart で表現する。機能は `frontend/` のルートと `backend/api` のルータ、`backend/service` のパイプラインに対応する。

## 全体ユースケース図

```mermaid
flowchart LR
    classDef actor fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef uc fill:#fff,stroke:#666,rx:18,ry:18;
    classDef sys fill:#f5f5f5,stroke:#999,stroke-dasharray:4 4;

    dev["👤 開発者<br/>(メンバー)"]:::actor
    lead["🧭 テックリード<br/>(オーナー/管理者)"]:::actor
    gh["🐙 GitHub<br/>(外部システム)"]:::actor
    twin["🤖 Twin Agent<br/>(自律ループ)"]:::actor

    subgraph SYS["🛰️ Rosetta システム"]
        direction TB

        subgraph ACC["アカウント / 組織"]
            u1(["GitHub でログイン"]):::uc
            u2(["組織・メンバーを管理"]):::uc
            u3(["プロジェクトを作成"]):::uc
            u4(["リポジトリを接続"]):::uc
        end

        subgraph DIAG["診断（理解する）"]
            u5(["リポジトリを解析する<br/>(コックピット)"]):::uc
            u6(["スタックを解析"]):::uc
            u7(["コード/知識負債を検知"]):::uc
            u8(["Overview 二軸ダッシュボードを見る"]):::uc
            u9(["負債マトリクスをドリルダウン"]):::uc
            u10(["知識ギャラクシーで KC を見る"]):::uc
        end

        subgraph REPAY["返済する"]
            u11(["クイズを生成・受験して返済"]):::uc
            u12(["返済 PR を生成"]):::uc
            u13(["学習プランを生成・検証"]):::uc
        end

        subgraph AGENT["エージェント"]
            u14(["Twin Agent の活動を観測"]):::uc
            u15(["自律ループを実行"]):::uc
        end

        subgraph REF["参照"]
            u16(["リポジトリ/コードを閲覧"]):::uc
        end
    end

    dev --> u1 & u3 & u4
    dev --> u5 & u8 & u9 & u10
    dev --> u11 & u14 & u16
    lead --> u2 & u12 & u13 & u15
    lead --> u8

    %% include 関係（コックピットが各生成を束ねる）
    u5 -.includes.-> u6
    u5 -.includes.-> u7
    u5 -.includes.-> u10
    u5 -.includes.-> u11
    u5 -.includes.-> u13
    u15 -.includes.-> u7
    u15 -.includes.-> u12

    %% 外部システム連携
    u1 -.認可.-> gh
    u4 -.App install.-> gh
    u6 -.REST/解析.-> gh
    u12 -.PR 作成.-> gh
    u15 --> twin
    twin -.検知→分析→計画→返済→検証.-> u7
```

## アクターと責務

| アクター | 説明 | 主なユースケース |
|---|---|---|
| 👤 開発者（メンバー） | プロジェクトに参加する一般開発者 | ログイン / プロジェクト作成 / リポジトリ接続 / 解析実行 / 各 Map 閲覧 / クイズ返済 / 活動観測 |
| 🧭 テックリード（オーナー/管理者） | 組織・チームを管理する責任者 | メンバー管理 / 返済 PR 生成 / 学習プラン / 自律ループ実行 / 全体ダッシュボード |
| 🐙 GitHub | OAuth・GitHub App・REST API を提供する外部システム | ログイン認可 / App インストール / リポジトリ読取 / PR 作成 |
| 🤖 Twin Agent | service 上で動く自律ループ（検知→分析→計画→返済→検証） | 各パイプラインを束ねナラティブ化 |

## ユースケース ↔ 実装対応

| ユースケース | フロント（ルート） | バックエンド（api ルータ / service パイプライン） |
|---|---|---|
| GitHub でログイン | `/login` | `auth`（GitHub OAuth + JWT/refresh cookie） |
| 組織・メンバーを管理 | `[org]/settings/members` | `orgs` / `users` |
| プロジェクトを作成 | `[org]/projects/new` | `projects` |
| リポジトリを接続 | `[org]/[project]/repos` | `github`（App installation） |
| リポジトリを解析する（コックピット） | `[org]/[project]`（Overview・issue-037） | 各 enqueue を束ねる |
| スタックを解析 | （Repos / Overview） | `stack` → `stack_analysis` |
| コード/知識負債を検知 | （Matrix） | `debts` / `knowledge_debts` → `code_debt_detection` / `knowledge_debt_detection` |
| Overview 二軸ダッシュボード | `[org]/[project]` | `overview` |
| 負債マトリクスをドリルダウン | `[org]/[project]/matrix/[debtId]` | `debts` |
| 知識ギャラクシーで KC を見る | `[org]/[project]/galaxy` | `galaxy` / `kc` → `kc_analysis` |
| クイズを生成・受験して返済 | `[org]/[project]/quizzes/[sessionId]/result` | `quizzes` → `quiz_generation` / `quiz_grading` |
| 返済 PR を生成 | （Matrix 詳細） | `debts` → `repayment_pr_generation` |
| 学習プランを生成・検証 | `[org]/[project]/learning` | `learning` → `learning_plan_generation` |
| Twin Agent の活動を観測 | `[org]/[project]/agents` | `agents` |
| 自律ループを実行 | `[org]/[project]/agents` | `agent_loop`（`code_debt_loop` / `knowledge_debt_loop`） |
| リポジトリ/コードを閲覧 | `[org]/[project]/repos` | `github` |

> 注: 各 Map の「生成を起動する UI」は issue-037（解析ラン・コックピット）で配線する。
> 現状は enqueue API（`client.ts`）は配線済みだが、UI 起点が未実装のものがある。
</content>
