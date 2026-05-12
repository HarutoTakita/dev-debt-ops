import { describe, expect, it, vi } from "vitest";
import { page } from "@vitest/browser/context";
import { render } from "vitest-browser-svelte";

vi.mock("$lib/paraglide/runtime", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, getLocale: () => "en" };
});

vi.mock("$app/paths", () => ({ resolve: (p: string) => p }));

vi.mock("$app/state", () => ({
  page: { status: 404, error: { message: "Not Found" }, params: {}, url: new URL("http://localhost/") },
}));

import ErrorPage from "./+error.svelte";

describe("ErrorPage", () => {
  it("renders the HTTP status, error message, and go-home link", async () => {
    render(ErrorPage);
    await expect.element(page.getByText("404")).toBeInTheDocument();
    await expect.element(page.getByText("Not Found")).toBeInTheDocument();
    await expect.element(page.getByRole("link", { name: "Go home" })).toBeInTheDocument();
  });
});
