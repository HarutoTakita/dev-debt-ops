# issue 067: 解析時にコード品質・理解度の推移スナップショットを記録する

## 概要
ダッシュボードの「コード品質と理解度の推移」ブロック（`debt-trend-strata.svelte`）は、`debt_trend_points`
テーブル（issue 031 で追加）を週次スナップショットとして表示する設計だが、**書き込み処理が未実装**のため
実プロジェクトでは常に空になっている（書き込みは元々 issue 037 = 撤回済みのエージェントループ担当だった）。
「解析」実行時に現在の集計を 1 点記録し、データがたまるまでは空状態メッセージを表示する。

## 背景・目的
- `backend/api/app/services/debt_query.py` は `debt_trend_points` を **読む**だけで、INSERT/upsert がコード
  ベースのどこにも存在しない（grep 済み）。結果、実データの推移ブロックは見出し＋凡例だけで中身が出ない。
- 推移（時系列で良くなっているか）はプロダクトの価値の一つ。最小実装で「解析を重ねるほど履歴が育つ」状態にする。
- 同時に、データが 1 点未満／少ない間は「壊れている」ように見えるため、空状態の案内を出す。

## 対応方針
1. **解析時に 1 点記録（option 1）**: 「解析」（`runAll`）完了後に、その時点のプロジェクト集計
   （ファイル単位の `code_debt_score` / `knowledge_coverage` の平均）を `debt_trend_points` に upsert。
   キーは `(project_id, week)`（`week` = その週の月曜日 ISO 日付）。同一週の再解析は上書き（=最新スナップショット）。
2. **空状態メッセージ（option 2）**: 推移は 2 点以上で初めて意味を持つため、`trend.length < 2` の間は
   バーの代わりに「解析を重ねると週ごとの推移が表示されます」という空状態を表示する。

## タスク
- [ ] backend(api): `debt_query.record_trend_snapshot(session, project, org_slug)` を追加。`build_overview` の
      `files` を再利用し、`code_debt_score` / `knowledge_coverage` の平均を算出。`(project_id, 今週)` で upsert。
      ファイルが 0 件（未解析）なら記録せず `None` を返す。
- [ ] backend(api): `POST /api/v1/orgs/{slug}/projects/{project_slug}/trend-snapshot` を追加（OrgScope）。
      記録した点（または `null`）を返す。
- [ ] frontend: `client.ts` に `recordTrendSnapshot(orgSlug, projectSlug)` を追加。
- [ ] frontend: `analysis-run-store.runAll` 完了後にスナップショットを記録（失敗してもランは壊さない）。
- [ ] frontend: `debt-trend-strata.svelte` で `trend.length < 2` の場合に空状態メッセージを表示。i18n（ja/en）追加。
- [ ] スキーマ変更なし（`debt_trend_points` は issue 031 / migration 0010 で既存）。Alembic マイグレーション不要。

## 完了条件
- 「解析」を実行すると、その週の推移点が `debt_trend_points` に記録／更新される。
- 別の週に再度解析すると点が増え、2 点以上たまるとダッシュボードに推移バーが表示される。
- 点が 2 点未満のときは空状態メッセージが表示され、「壊れている」ように見えない。
- `bun run check` / `bun run lint` / `bun run test:unit`、backend の ruff/ty/pytest が通る。

## 非対象（将来）
- 週次の定期スナップショット（Cloud Functions による cron 生成）— 本 issue は解析トリガーのみ。
- 過去の `analysis_run` 履歴からのバックフィル。
- 日次など週より細かい粒度（テーブルは週単位の一意制約）。
