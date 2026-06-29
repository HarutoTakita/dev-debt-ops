// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
  namespace App {
    // interface Error {}
    // interface Locals {}
    // interface PageData {}
    // interface PageState {}
    // interface Platform {}
  }

  // package.json の version を vite.config.ts の define で埋め込む（ビルド時定数）。
  const __APP_VERSION__: string;
}

export {};
