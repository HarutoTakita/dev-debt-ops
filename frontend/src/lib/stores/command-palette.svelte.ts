// コマンドパレットの開閉状態を共有するストア。⌘K / `/`（キーボードショートカット）とトリガーボタンの
// 双方から同じ状態を操作するため、トリガー内にあったローカル state をここへ引き上げた。
class CommandPaletteStore {
  open = $state(false);

  toggle() {
    this.open = !this.open;
  }
}

export const commandPalette = new CommandPaletteStore();
