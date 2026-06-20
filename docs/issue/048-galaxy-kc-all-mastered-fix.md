# ギャラクシーが全て「マスター済み」になる KC 判定を是正する

## 概要
Knowledge Galaxy のマップビューで、**ほぼ全てのスター（ファイル）が「マスター済み」**になり、知識被覆（KC）のギャップ（black_hole / dim_star）が現れない。KC が「著者であること（authorship）」だけから算出され、リポジトリ作成者は自分のコードを全て高 KC＝star と判定されるため。

## 背景・目的
ギャラクシーは「どこに理解負債があるか」を見せる画面。著者＝マスターという単純化では、個人リポジトリで全マスターになり、知識負債という製品価値そのものが消える。KC を「実際の理解度」に近づけ、ギャップが見える状態にする。

## タスク
- [ ] KC 算出モデルを見直す: 現状 authorship（blame 行シェア）由来の KC のみで `kc >= 0.7 → star → mastered` となる。著者であることをそのまま「マスター」と等価にしない方針を定める（例: authorship 由来は上限を設ける／quiz・review 認定と分離して扱う）。
- [ ] `mastered` の定義を再検討する: 現状 `mastered = (mastery == "star")` かつ star は KC>=0.7。スキーマのコメントどおり「クイズ未連携のため暫定」なので、quiz 認定（`certified_via=quiz`）連携後の本来定義に寄せる（[040]/クイズ連携と整合）。
- [ ] `observed=false`（KC ラン未実行）時の表示を「全マスター」ではなく「未観測（要解析）」として明示し、モック/既定値で誤解を生まないようにする。
- [ ] しきい値（star>=0.7 / dim_star 0.4-0.7 / black_hole<0.4+接触 / unexplored 無接触）が実データ分布に対して妥当か検証し、必要なら調整する。
- [ ] フロントの凡例・表示が新しい判定と整合するよう更新する（個人 KC と org KC、認定経路の区別）。

## 完了条件
- 実プロジェクトで、著者であることだけを根拠に全ファイルが「マスター済み」にならない。
- 知識被覆のギャップ（black_hole / dim_star）が妥当に出現し、ギャラクシーが理解負債を可視化できている。
- KC ラン未実行時は「未観測」と明示され、マスター済みと誤認されない。

## 技術詳細
- しきい値ロジック: `backend/service/service/pipelines/kc_analysis.py:63-74`（`mastery_from_kc()`）。
- 集計: 同 `:239-251` — `dev_ratios` があれば `KC = max(dev_kcs)`（authorship 由来）、無ければ 0.0。
- API 側: `backend/api/app/services/galaxy_query.py:70` `mastered = (mastery == "star")`、未接触は `unexplored`/`kc=0.0`。
- スキーマ注記（暫定の根拠）: `frontend/src/lib/api/schemas.ts:294`「§5.5 個人認定の簡易版: クイズ未連携のため mastery==="star" を「マスター済み」表示」。
- 取得経路: `frontend/src/lib/stores/galaxy-store.svelte.ts:17-19` → `getGalaxy()`（`frontend/src/lib/api/client.ts:397-401`）→ `GET /api/v1/orgs/{slug}/projects/{project_slug}/galaxy`（`backend/api/app/api/v1/galaxy.py:26-41`）。

## 参考
- 関連: [009 Knowledge Galaxy](./009-knowledge-galaxy-2d-map.md)、[029 KC 算出パイプライン](./029-backend-kc-knowledge-coverage-pipeline.md)、[032 Galaxy 個人 KC API](./032-backend-galaxy-personal-kc-api.md)、[034 クイズ生成・採点](./034-backend-quiz-generation-and-grading-pipelines.md)
- 依存: クイズ認定連携（KC を quiz 結果で更新）と整合させる。
- 想定ラベル: `bug`, `backend`
