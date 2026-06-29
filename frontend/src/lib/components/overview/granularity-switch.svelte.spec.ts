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

  it("does not render the removed class/function granularities", async () => {
    render(GranularitySwitch, { value: "file", onChange: () => {} });
    await expect.element(page.getByRole("button", { name: "ファイル" })).toBeInTheDocument();
    expect(page.getByRole("button", { name: "クラス" }).query()).toBeNull();
    expect(page.getByRole("button", { name: "関数" }).query()).toBeNull();
  });
});
