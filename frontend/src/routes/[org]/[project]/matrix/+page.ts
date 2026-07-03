import type { DebtFilter } from "$lib/api/client";
import type { PageLoad } from "./$types";

export const ssr = false;

// Overview マトリクスのセル/象限クリック → /[org]/matrix?cell=...&kind=...&priority=... の入口。
// クエリからフィルタ初期値を組み立てる。
function parseFilter(url: URL): DebtFilter {
  const list = (key: string): string[] | undefined => {
    const v = url.searchParams.get(key);
    return v ? v.split(",").filter(Boolean) : undefined;
  };
  const filter: DebtFilter = {};
  const kind = list("kind");
  if (kind) filter.kind = kind as ("code" | "knowledge")[];
  const priority = list("priority");
  if (priority) filter.priority = priority as ("P0" | "P1" | "P2" | "P3")[];
  const agent = list("agent");
  if (agent) filter.agent = agent;
  const status = list("status");
  if (status) filter.status = status;
  return filter;
}

export const load: PageLoad = ({ params, url }) => {
  return {
    orgSlug: params.org,
    projectSlug: params.project,
    initialFilter: parseFilter(url),
    cell: url.searchParams.get("cell"),
  };
};
