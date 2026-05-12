import * as m from "$lib/paraglide/messages";

const codeMap: Record<string, () => string> = {
  ORG_NOT_FOUND: () => m.toast_org_not_found(),
};

export function translateBackendError(detail: string): string {
  const mapped = codeMap[detail];
  return mapped ? mapped() : detail;
}
