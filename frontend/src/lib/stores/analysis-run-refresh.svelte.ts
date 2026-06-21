import { analysisRun, type StageId } from "$lib/stores/analysis-run-store.svelte";

// 解析ラン完了 → 画面の自動リフレッシュ共通パターン（issue 049）。
// 指定ステージが COMPLETED へ遷移するたびに fn を「1 ラン 1 回だけ」呼ぶ $effect を張る。
//
// 多重発火ガード: ステージごとに「直近に処理した jobId」を記録し、同一完了では再実行しない。
// 新しいラン（再解析・プロジェクト切替）は jobId が変わるため再び発火する。fn が更新する
// 状態（ストア/ローカル）は $effect 内で読まないため、再取得が次の発火を呼ぶ無限ループは起きない。
//
// コンポーネント初期化時（<script> トップレベル）に呼ぶこと（$effect の制約）。
export function refreshOnStageComplete(stageIds: StageId[], fn: () => void): void {
  // 非リアクティブなガード（プレーンオブジェクト）。stageId -> 直近に処理した jobId。
  // ここをリアクティブ（SvelteMap 等）にすると $effect が自分の書き込みで再実行され不要。
  const handled: Partial<Record<StageId, string | null>> = {};
  $effect(() => {
    for (const id of stageIds) {
      const st = analysisRun.stages[id];
      if (st?.status === "COMPLETED" && handled[id] !== st.jobId) {
        handled[id] = st.jobId;
        fn();
      }
    }
  });
}
