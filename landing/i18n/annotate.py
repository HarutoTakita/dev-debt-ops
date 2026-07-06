#!/usr/bin/env python3
"""index.html の翻訳対象要素に data-i18n="key" を付与する（1回限りのユーティリティ）。
各エントリ (key, tag, anchor) について、anchor（本文中で一意な部分文字列）を含む
最も近い祖先 <tag ...> の開始タグに data-i18n を挿入する。anchor は一意でなければ失敗する。"""
import re
import sys

PATH = "index.html"
html = open(PATH, encoding="utf-8").read()

# (key, tag, anchor) — anchor は index.html 内で一意な文字列（多くは日本語原文そのもの）。
ENTRIES = [
    ("nav.how", "a", ">仕組み<"),
    ("nav.features", "a", ">機能<"),
    ("nav.infra", "a", ">インフラ<"),
    ("nav.security", "a", ">セキュリティ<"),
    ("nav.cta", "a", ">デモを体験する<"),

    ("hero.sub", "p", "コードベースの理解度を実測・促進する開発プラットフォーム"),
    ("hero.h1", "h1", "クイズで<span class=\"text-know\">理解度</span>を実測し"),
    ("hero.lead", "p", "AI エージェントが<strong class=\"font-semibold text-white\">サブエージェント"),
    ("hero.chip1", "span", "AIエージェント × MCP で高度なリポジトリ探索"),
    ("hero.chip2", "span", "GitHub 連携でかんたんログイン"),
    ("hero.chip3", "span", "PII・シークレットを自動マスキング"),
    ("hero.chip4", "span", ">\n              モバイル対応\n"),
    ("hero.chip5", "span", "スケーラブルなインフラ構成"),

    ("challenge.h2", "h2", "AI 時代に急速に積み上がる「理解負債」"),
    ("challenge.lead", "p", "Claude Code・Codex・Gemini CLI などの普及で"),
    ("challenge.c1t", "h3", "「動けばよい」で理解が置き去り"),
    ("challenge.c1d", "p", "納期とデプロイ速度が優先され"),
    ("challenge.c2t", "h3", "AI 任せで思考がスキップされる"),
    ("challenge.c2d", "p", "もっともらしい生成コードをそのまま信頼し"),
    ("challenge.c3t", "h3", "「理解しているか」は測られない"),
    ("challenge.c3d", "p", "レビューやテストは品質を測っても"),

    ("audience.h2", "h2", ">こんな方に<"),
    ("audience.a1t", "h3", "テックリード / マネージャー"),
    ("audience.a1d", "p", "チームメンバーの理解度が低い箇所を把握し"),
    ("audience.a2t", "h3", "オンボーディング担当 / 新規参画メンバー"),
    ("audience.a2d", "p", "どこから理解すべきかを、学習ユニットとクイズで"),

    ("flow.h2", "h2", "開発・運用のサイクルに、技術負債・理解負債の解消を取り込む"),
    ("flow.sub", "p", "解析から、理解の実測・品質の検知、学習・改善までを一気通貫"),
    ("flow.s0t", "div", ">リポジトリ解析<"),
    ("flow.s0d", "div", "AI エージェントが MCP を使ってコードベースを横断探索"),
    ("flow.track_know", "span", "track-tag know\">理解負債"),
    ("flow.track_code", "span", "track-tag code\">技術負債"),
    ("flow.s1t", "div", ">クイズを生成・実測<"),
    ("flow.s1d", "div", "機能ごとに理解度クイズを自動生成"),
    ("flow.s2t", "div", ">学習プランを生成<"),
    ("flow.s2d", "div", "理解が浅い機能に合わせ、該当コードのウォークスルー"),
    ("flow.s3t", "div", ">低品質コードの検知<"),
    ("flow.s3d", "div", "重複・複雑度・デッドコード・AI 生成痕跡などを解析し"),
    ("flow.s4t", "div", ">コード改善を提案<"),
    ("flow.s4d", "div", "低品質コードに対し AI が自動で修正 PR を作成"),
    ("flow.s5t", "div", ">理解度・品質が向上<"),
    ("flow.s5d", "div", "の両輪で属人化を解消し、コードベースの理解度とコード品質を継続的に向上"),

    ("core.h2", "h2", ">3 つのコア機能<"),
    ("core.c1t", "h3", "AI エージェントによる高度なリポジトリ解析"),
    ("core.c1d", "p", "Google ADK で構築したエージェントが MCP（Serena"),
    ("core.c2t", "h3", "理解負債の可視化 × クイズと学習で改善"),
    ("core.c2d", "p", "ソースコードを機能単位にクラスタリングし、機能ごとに学習プラン"),
    ("core.c3t", "h3", "低品質コードへの推奨提案と自動修正"),
    ("core.c3d", "p", "解析で検出した低品質コードに対し、推奨事項を GitHub Issue"),
    ("core.oplabel", "p", ">実運用を見据えた機能<"),
    ("core.pill1", "span", "GitHub SSO 認証・認可"),
    ("core.pill2", "span", ">プロジェクト管理\n"),
    ("core.pill3", "span", ">オンボーディングガイド\n"),
    ("core.pill4", "span", ">豊富なショートカット\n"),
    ("core.pill5", "span", "管理者によるユーザー管理"),
    ("core.pill6", "span", "クレジット付与による課金制御"),
    ("core.pill7", "span", "i18n 多言語対応"),
    ("core.pill8", "span", "リリース履歴の確認"),

    ("features.h2", "h2", ">アプリにできること<"),
    ("features.sub", "p", "解析からダッシュボード、可視化、改善までを 1 つのワークスペースで"),
    ("features.f1t", "h3", "ダッシュボード — 全体像を一目で"),
    ("features.f1lead", "p", "リポジトリの理解度とコード品質を一枚で確認できます。"),
    ("features.f1li1", "li", "はファイルを「理解度 ×"),
    ("features.f1li2", "li", "は理解度・低品質ファイル件数・修正済み件数を変化量つきで表示"),
    ("features.f1li3", "li", "でコード品質と理解度の時間変化を確認"),
    ("features.f1li4", "li", "で対応すべきファイルを一覧"),
    ("features.f1tag1", "span", "理解度 × 品質の二軸"),
    ("features.f1tag2", "span", "ホットスポット可視化"),
    ("features.f1tag3", "span", "優先対応スコア"),
    ("features.f2t", "h3", "理解度マップ — 誰がどこを分かっているか"),
    ("features.f2lead", "p", "機能・ファイル別に、ユーザーの理解度をグラフで可視化します"),
    ("features.f2leg1", "li", ">理解済み<"),
    ("features.f2leg2", "li", ">部分理解<"),
    ("features.f2leg3", "li", ">未理解<"),
    ("features.f2leg4", "li", ">未着手<"),
    ("features.f2tag1", "span", "CodeGraphContext によるグラフ可視化"),
    ("features.f2tag2", "span", "ファイル間の依存関係解析"),
    ("features.f2tag3", "span", ">機能クラスタリング<"),
    ("features.f3t", "h3", "コード品質マップ — 品質の分布を俯瞰"),
    ("features.f3lead", "p", "ソースコードをファイル単位で閲覧し、どのファイルにどのような"),
    ("features.f3li1", "li", "からファイルを選択。改善余地があるファイルには"),
    ("features.f3li2", "li", "・右側に選んだファイルの中身を表示"),
    ("features.f3tag1", "span", "Serena MCP（LSP）による解析"),
    ("features.f3tag2", "span", "Semgrep による静的解析"),
    ("features.f3tag3", "span", ">デッドコード検知<"),
    ("features.f4t", "h3", "クイズと学習 — 実測して理解を深める"),
    ("features.f4lead", "p", "機能ごとの学習プランを受講し、確認クイズで理解度をチェックします"),
    ("features.f4li1", "li", "・学習プラン一覧</strong>"),
    ("features.f4li2", "li", "・学習を開く</strong>"),
    ("features.f4li3", "li", "・理解度を確認する</strong>"),
    ("features.f4tag1", "span", "ADK エージェントが学習プラン・クイズを生成"),
    ("features.f4tag2", "span", "リポジトリ特有 × 技術スタックの両輪で学習"),
    ("features.f4tag3", "span", "フラグ付け・誤答の再テスト"),
    ("features.f5t", "h3", "コード改善 — PR / Issue で返す"),
    ("features.f5lead", "p", "ファイル単位で改善箇所を確認し、AI による修正 Pull Request"),
    ("features.f5li1", "li", "で絞り込み、<strong class=\"text-white\">優先度順"),
    ("features.f5li2", "li", "・詳細画面では問題のコード箇所がハイライトされ"),
    ("features.f5li3", "li", "・改善方法は<strong class=\"text-white\">「AI に修正 PR を自動作成」"),
    ("features.f5tag1", "span", "AI が修正パッチを生成"),
    ("features.f5tag2", "span", ">修正 PR 自動生成<"),
    ("features.f5tag3", "span", ">GitHub Issue 起票<"),

    ("infra.h2", "h2", ">インフラ構成<"),
    ("infra.lead", "p", "Cloud Tasks を活用して解析は非同期ワーカーへ分離"),

    ("security.h2", "h2", "セキュリティでこだわっていること"),
    ("security.s1t", "h3", ">認証・セッション<"),
    ("security.s1d", "p", "JWT トークンを用いた GitHub SSO"),
    ("security.s2t", "h3", "同一オリジン配信と Web 脆弱性対策"),
    ("security.s2d", "p", "UIとAPIを同一オリジンで配信することで"),
    ("security.s3t", "h3", ">鍵を持たない設計<"),
    ("security.s3d", "p", "Workload Identity Federation で長期クレデンシャルを排除"),
    ("security.s4t", "h3", "エッジおよびアプリ内でのレート制限"),
    ("security.s4d", "p", "Cloud Armor によりアプリ手前で過剰なリクエストを制限"),
    ("security.s5t", "h3", "エージェント入力のマスキング"),
    ("security.s5d", "p", "エージェントに情報を与える際は、Cloud DLP"),
    ("security.s6t", "h3", ">脆弱性スキャン<"),
    ("security.s6d", "p", "OWASP に準拠したアプリケーションの脆弱性スキャン"),

    ("mobile.h2", "h2", "スマホでも、いつでも理解度をチェック"),
    ("mobile.sub", "p", "レスポンシブ対応で、スマートフォンからも主要機能をそのまま利用可能"),
    ("mobile.l1", "figcaption", "font-semibold text-white\">ダッシュボード<"),
    ("mobile.l2", "figcaption", "font-semibold text-know\">理解度マップ<"),
    ("mobile.l3", "figcaption", "font-semibold text-code\">コード品質マップ<"),
    ("mobile.l4", "figcaption", "font-semibold text-know\">クイズと学習<"),
    ("mobile.l5", "figcaption", "font-semibold text-code\">コード改善<"),

    ("stack.h2", "h2", ">技術スタック<"),

    ("cta.h2", "h2", "チームの理解度を、今日から見える化"),
    ("cta.p", "p", "GitHub リポジトリを接続して解析するだけ。理解負債と技術負債"),
    ("cta.btn", "a", "リポジトリを接続して始める"),

    ("footer.privacy", "button", ">\n            プライバシーポリシー\n"),

    ("privacy.title", "h2", ">プライバシーポリシー<"),
    ("privacy.intro", "p", "DevDebtOps（以下「本サービス」といいます）は、本サービスの利用者"),
    ("privacy.1t", "h3", ">1. 取得する情報<"),
    ("privacy.1li1", "li", "アカウント情報</span>：GitHub 連携によるログイン時"),
    ("privacy.1li2", "li", "解析対象データ</span>：利用者が接続した GitHub"),
    ("privacy.1li3", "li", "利用データ</span>：クイズの回答・学習の進捗"),
    ("privacy.2t", "h3", ">2. 利用目的<"),
    ("privacy.2li1", "li", "本サービスの提供・運営（理解度の実測、コード解析"),
    ("privacy.2li2", "li", "本サービスの品質向上、機能改善および不具合への対応"),
    ("privacy.2li3", "li", "不正利用の防止、セキュリティの確保および利用状況の分析"),
    ("privacy.3t", "h3", ">3. 外部サービスとの連携<"),
    ("privacy.3p", "p", "本サービスは、機能提供のため以下の外部サービスと連携します"),
    ("privacy.3li1", "li", "GitHub</span>：認証およびリポジトリ連携のため"),
    ("privacy.3li2", "li", "AI 解析基盤（Google Vertex AI / Gemini 等）</span>"),
    ("privacy.4t", "h3", ">4. 第三者提供<"),
    ("privacy.4p", "p", "法令に基づく場合その他正当な理由がある場合を除き"),
    ("privacy.5t", "h3", ">5. 組織アカウント経由の利用<"),
    ("privacy.5p", "p", "利用者が所属する組織（チーム・企業等）を通じて"),
    ("privacy.6t", "h3", ">6. 保管とセキュリティ<"),
    ("privacy.6p", "p", "取得した情報は、暗号化・アクセス制御等の適切な"),
    ("privacy.7t", "h3", ">7. 保持期間と削除<"),
    ("privacy.7p", "p", "情報は利用目的の達成に必要な期間保持し"),
    ("privacy.8t", "h3", ">8. 越境データ移転<"),
    ("privacy.8p", "p", "本サービスはクラウド基盤（Google Cloud）および AI 解析基盤を利用"),
    ("privacy.9t", "h3", "9. 処理の法的根拠（EEA / 英国の利用者向け）"),
    ("privacy.9p", "p", "欧州経済領域（EEA）または英国の利用者について"),
    ("privacy.10t", "h3", ">10. 利用者の権利<"),
    ("privacy.10p", "p", "利用者は、自己の個人情報について、開示・訂正・削除"),
    ("privacy.11t", "h3", ">11. Cookie の利用<"),
    ("privacy.11p", "p", "本サービスは、ログイン状態の維持およびセキュリティ確保に必要な Cookie"),
    ("privacy.12t", "h3", ">12. 本ポリシーの改定<"),
    ("privacy.12p", "p", "本ポリシーは、法令の変更やサービス内容の変更に応じて改定"),
    ("privacy.13t", "h3", ">13. お問い合わせ<"),
    ("privacy.13p", "p", "本ポリシーに関するお問い合わせは、本サービスの運営者"),
    ("privacy.updated", "p", "最終更新日：2026 年 7 月 6 日"),
]

errors = []
for key, tag, anchor in ENTRIES:
    n = html.count(anchor)
    if n != 1:
        errors.append(f"{key}: anchor count={n} :: {anchor!r}")
        continue
    idx = html.index(anchor)
    # anchor を内包する最も近い開始タグ <tag ...> を後方検索
    opens = [m for m in re.finditer(r"<" + tag + r"(?=[\s>])", html[:idx])]
    if not opens:
        errors.append(f"{key}: no opening <{tag}> before anchor")
        continue
    start = opens[-1].start()
    gt = html.index(">", start)
    tagtext = html[start:gt]
    if "data-i18n=" in tagtext:
        errors.append(f"{key}: tag already has data-i18n")
        continue
    html = html[:gt] + f' data-i18n="{key}"' + html[gt:]

if errors:
    print("ERRORS:")
    print("\n".join(errors))
    sys.exit(1)

open(PATH, "w", encoding="utf-8").write(html)
print(f"OK: annotated {len(ENTRIES)} elements")
