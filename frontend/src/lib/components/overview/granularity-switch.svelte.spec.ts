import { describe, expect, it, vi } from "vitest";
import { page } from "@vitest/browser/context";
import { render } from "vitest-browser-svelte";
import GranularitySwitch from "./granularity-switch.svelte";

describe("GranularitySwitch", () => {
  it("calls onChange with the picked granularity", async () => {
    const onChange = vi.fn();
    render(GranularitySwitch, { value: "file", onChange });
    await page.getByRole("button", { name: "機能" }).click();
    expect(onChange).toHaveBeenCalledWith("feature");
  });

  it("renders class/function as disabled (coming soon)", async () => {
    render(GranularitySwitch, { value: "file", onChange: () => {} });
    await expect.element(page.getByRole("button", { name: "クラス" })).toBeDisabled();
    await expect.element(page.getByRole("button", { name: "関数" })).toBeDisabled();
  });
});
