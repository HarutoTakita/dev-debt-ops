import { defineConfig } from "@playwright/test";

const externalBaseURL = process.env.BASE_URL;

export default defineConfig({
  use: externalBaseURL ? { baseURL: externalBaseURL } : undefined,
  webServer: externalBaseURL ? undefined : { command: "bun run build && bun run preview", port: 4173 },
  testMatch: "**/*.e2e.{ts,js}",
  // Serial: the suite targets one shared backend stack (Traefik rate-limit buckets,
  // the shared test user, cookies). Parallel workers race on that state and flake.
  workers: 1,
});
