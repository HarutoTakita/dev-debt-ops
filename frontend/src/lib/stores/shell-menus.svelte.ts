// シェル上部メニュー/パネルの開閉状態を共有するストア。オンボーディングガイドが
// 「各種設定」「言語」「解析」「ヘルプ」ステップで該当メニューを確実に開いてハイライトするために使う
// （bits-ui の hover 駆動サブメニューやポップオーバーを、synthetic click に頼らず決定的に開く）。
// 通常操作でもトリガーの開閉と双方向バインドするため、非ツアー時は普通のメニュー状態として機能する。
class ShellMenus {
  analysisPanel = $state(false); // 解析ポップオーバー
  userMenu = $state(false); // 右上ユーザーメニュー
  userLanguage = $state(false); // ユーザーメニュー内「言語」サブメニュー
  helpMenu = $state(false); // サイドバー左下ヘルプメニュー
  shortcutList = $state(false); // ? のショートカット一覧ダイアログ
  changelog = $state(false); // 変更履歴（チェンジログ）ダイアログ

  reset() {
    this.analysisPanel = false;
    this.userMenu = false;
    this.userLanguage = false;
    this.helpMenu = false;
    this.shortcutList = false;
    this.changelog = false;
  }
}

export const shellMenus = new ShellMenus();
