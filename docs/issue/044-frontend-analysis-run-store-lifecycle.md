# analysis-run シングルトンのライフサイクルと Overview フォールバックの是正

## 概要 / 重大度

**重大度: High（クロスページ状態リーク・ポーリング誤中断）。**

issue-037 で新設した `analysis-run-store` はモジュールシングルトンで、Overview/Matrix/Galaxy/
Learning/Agents が共有する。コンポーネント寿命に紐づく `cancel()`・project 切替で reset されない
状態・並行 `runAll` の競合が、ポーリングの誤中断やプロジェクト間の状態漏れを生む。

## 該当箇所と問題

### A. cockpit の `onDestroy(cancel)` が他ページのポーリングを殺す（High）
- `frontend/src/lib/components/overview/analysis-run-cockpit.svelte:41` →
  `analysis-run-store.svelte:133-135`（`cancel()` が `#generation` を増分し全 in-flight poll を中断）。
- Galaxy（`coming-soon-placeholder.svelte`）や Matrix（`matrix/+page.svelte:113`）が同シングルトンで
  起動したステージが、cockpit unmount 時に**無言で中断**され `QUEUED/PROCESSING` のまま固着。
- **修正**: シングルトンの中断をひとつのコンポーネント寿命に縛らない。案: (a) ポーリングを
  ページ単位インスタンス化、(b) cockpit は自分が起動したステージのみ cancel、(c) `onDestroy` cancel を
  撤廃し terminal まで走らせる。いずれかを採用。

### B. project 切替でシングルトンが reset されない（High）
- `analysis-run-store.svelte`（`export const analysisRun = new AnalysisRunStore()`）+
  `[org]/[project]/+layout.svelte:31-37`（cleanup で `repo` はリセットするが `analysisRun` は未処理）。
- project A の COMPLETED 状態・deep-link が project B の cockpit に表示される。
- **修正**: layout cleanup（既存 `untrack` 内）で `analysisRun.reset()` を呼ぶ。

### C. Learning の遷移 effect が古い deep-link で誤遷移し得る（High）
- `learning/+page.svelte:30-38` — `plan_learning` が COMPLETED かつ `generating` のとき `goto(st.link)`。
  シングルトン未 reset だと前 project の `plan_id` を含む link に遷移し得る。A の中断と相まって
  `generating` が true のまま固着し得る。
- **修正**: B の reset で大半解消。加えて effect は「自分が起動した job/plan id」をキーに判定し、
  共有ステージ status だけで遷移しない。

### D. 並行 `runAll`/`runStage` の相互排他が無い（High→Medium）
- `analysis-run-store.svelte:81-105` — `#set` は read-modify-write。複数ページ/cockpit からの並行
  `runAll` が互いの patch を上書きし、stale な `depsOk` で依存ステージを走らせ得る。
  cockpit 主 CTA（`analysis-run-cockpit.svelte:48`）は `running` ガードが無く二重起動可能。
- **修正**: 「実行中ランの単一化」ガード（単一 run promise）。cockpit 主 CTA も `disabled={running}`。

### E. Overview の再スキャンループ（Medium）
- `[org]/[project]/+page.svelte:29-44` + `+layout.svelte:16-37` — layout が navigation 毎に
  `repo.connect()`（`scanState="scanning"`）を呼び、Overview が 2s タイマーで `finishScan()`、
  既スキャン済みでも戻る度にブラー placeholder が再表示。
- **修正**: 同一 repo に既接続なら `repo.connect` で `scanState` を `"scanning"` に戻さない
  （初回接続時のみ scan 演出）。

### F. 取得失敗が空とみなされ mock を実データ風に表示（Medium）
- `[org]/[project]/+page.svelte:42-44`（`.catch(() => overview = null)` → `overviewMock` を `isSample` 表示）。
  galaxy（`+page.svelte:22`）・agents（`+page.svelte:19`）も同様の握り潰し。
- **修正**: エラーと空を区別し、失敗時はエラー/リトライ状態を出す（mock を失敗フォールバックにしない）。

### G. `gap_concepts` を値でキーした `{#each}` は重複でクラッシュ（Medium）
- `learning/+page.svelte:65` — `{#each plan.gap_concepts as concept (concept)}`。重複値で Svelte 実行時エラー。
- **修正**: index キー、または描画前に dedupe。

### H. cockpit 主 CTA の二重起動ガード（Medium・D に内包）
- `analysis-run-cockpit.svelte:48` に `disabled={analysisRun.running}` を付与。

## 受け入れ条件

- A/B/C: project 切替後に前 project の状態が残らない・他ページ起動のポーリングが cockpit unmount で
  中断されない（`*.svelte.spec.ts` のストアテスト + 必要なら軽い結合テスト）。
- E: 既スキャン済み project に戻ってもブラー placeholder が再発しない。
- F: 取得失敗時に mock が「実データ風」に出ない。
- G: 重複 gap_concept でクラッシュしない。
- `bun run check`（0 warn）/ `lint` / `test:unit` 緑。

## 対象外

- stack-analysis-store の統合（別途検討。本 issue は analysis-run に集中）。
