import { describe, expect, it } from "vitest";
import { page } from "@vitest/browser/context";
import { render } from "vitest-browser-svelte";
import { createRawSnippet } from "svelte";
import FormField from "./form-field.svelte";

const inputSnippet = (id: string) =>
  createRawSnippet(() => ({
    render: () => `<input id="${id}" data-testid="field-input-${id}" />`,
  }));

describe("FormField", () => {
  it("renders label bound to the slotted input by id", async () => {
    const { container } = render(FormField, {
      id: "email-field",
      label: "Email",
      children: inputSnippet("email-field"),
    });
    await expect.element(page.getByText("Email")).toBeInTheDocument();
    const label = container.querySelector("label");
    expect(label).not.toBeNull();
    expect(label?.getAttribute("for")).toBe("email-field");
    expect(label?.textContent).toContain("Email");
  });

  it("does not render error paragraph when errors is empty or undefined", async () => {
    const { container } = render(FormField, {
      id: "field",
      label: "X",
      children: inputSnippet("field"),
    });
    // Wait for initial render to commit, then assert no alert exists.
    await expect.element(page.getByText("X")).toBeInTheDocument();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it("renders the first error with role=alert when errors has items", async () => {
    render(FormField, {
      id: "field2",
      label: "X",
      errors: ["First problem", "Second problem"],
      children: inputSnippet("field2"),
    });
    const alert = page.getByRole("alert");
    await expect.element(alert).toBeInTheDocument();
    await expect.element(alert).toHaveTextContent("First problem");
  });

  it("error element has id derived from field id", async () => {
    render(FormField, {
      id: "foo",
      label: "L",
      errors: ["oops"],
      children: inputSnippet("foo"),
    });
    await expect.element(page.getByRole("alert")).toHaveAttribute("id", "foo-error");
  });
});
