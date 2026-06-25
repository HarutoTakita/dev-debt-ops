// 新規プロジェクト作成モーダルの開閉状態。プロジェクト一覧・サイドバーなど、どこからでも開けるよう
// グローバルなシングルトンにする（別ページではなくモーダルで作成する）。
class ProjectCreateStore {
  open = $state(false);
}

export const projectCreate = new ProjectCreateStore();
