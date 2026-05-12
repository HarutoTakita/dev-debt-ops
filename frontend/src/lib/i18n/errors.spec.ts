import { describe, expect, it, vi } from "vitest";

let currentLocale: "ja" | "en" = "ja";
vi.mock("$lib/paraglide/runtime", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    getLocale: () => currentLocale,
  };
});

import { translateBackendError } from "./errors";

describe("translateBackendError", () => {
  it("maps ORG_NOT_FOUND to Japanese when locale is ja", () => {
    currentLocale = "ja";
    expect(translateBackendError("ORG_NOT_FOUND")).toBe("組織が見つかりませんでした");
  });

  it("maps ORG_NOT_FOUND to English when locale is en", () => {
    currentLocale = "en";
    expect(translateBackendError("ORG_NOT_FOUND")).toBe("Organization not found");
  });

  it("returns the raw detail when the code is unknown", () => {
    currentLocale = "ja";
    expect(translateBackendError("SOMETHING_UNKNOWN")).toBe("SOMETHING_UNKNOWN");
  });
});
