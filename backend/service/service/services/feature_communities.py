"""Graph-community re-alignment for feature clustering (issue 293, 方針A).

The Base Analysis Agent (or the fallback clustering model) authors *semantic* features with
human-readable names, but its file memberships are its free-form judgment and often leave a feature
with only 1–2 files. This module re-aligns those memberships to the repository's **call/import graph**
so each feature covers a connected, hub-centered region of related code — i.e. graph communities that
roughly match the feature clusters.

Approach: **seeded label propagation.** The LLM's per-feature files are the *seeds* (fixed community
anchors); every other file joins the feature most common among its already-labeled graph neighbors,
iterated to a fixed point. Pure, deterministic (sorted node order, ties broken by smallest key), and
bounded — no I/O, no model calls. The graph (file↔file edges) already exists at clustering time
(CGC ``file_edges`` in the agentic run; the import graph in the standalone run), so this adds no fetch.

The original LLM memberships are *preserved* (multi-membership kept): the returned set for a feature is
its seed files ∪ the files that propagated to it. Callers add the propagated members at a lower
confidence to keep the LLM-asserted files distinguishable.
"""

from collections import Counter, defaultdict
from collections.abc import Collection, Iterable, Mapping

_MAX_ITERS = 20  # label propagation converges well before this on repo-sized graphs; a safety bound.


def assign_communities(
    seeds: Mapping[str, Iterable[str]],
    edges: Iterable[tuple[str, str]],
    valid_paths: Collection[str],
    *,
    max_iters: int = _MAX_ITERS,
) -> dict[str, set[str]]:
    """Grow each seeded feature along the file graph via seeded label propagation.

    Args:
        seeds: ``feature_key -> seed file paths`` (the LLM's per-feature files).
        edges: undirected file↔file edges ``(a, b)`` (import/call graph); direction is ignored.
        valid_paths: the set of real repo file paths; endpoints/seeds outside it are dropped.
        max_iters: safety bound on propagation rounds.

    Returns:
        ``feature_key -> members``, where members = seed files ∪ files that propagated to the feature.
        Multi-membership is preserved (a file may appear under several features).
    """
    valid = set(valid_paths)

    # Undirected adjacency over valid paths only (drop unknown endpoints + self-edges).
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in edges:
        if a in valid and b in valid and a != b:
            adj[a].add(b)
            adj[b].add(a)

    # Seed labels: anchor each seeded file to a single *primary* feature (deterministic: smallest key
    # when one file seeds multiple features) so propagation has fixed community centers. The file's
    # original multi-membership is kept separately in ``seed_members`` and merged back at the end.
    label: dict[str, str] = {}
    seed_members: dict[str, set[str]] = {}
    for key in sorted(seeds):
        members = {p for p in seeds[key] if p in valid}
        seed_members[key] = set(members)
        for p in members:
            label.setdefault(p, key)
    anchors = set(label)  # seeds stay fixed during propagation

    # Label propagation: an unlabeled node joins the feature most common among its labeled neighbors
    # (ties → smallest key). Deterministic node order; bounded iterations.
    for _ in range(max_iters):
        changed = False
        for node in sorted(valid):
            if node in anchors:
                continue
            counts = Counter(label[n] for n in adj.get(node, ()) if n in label)
            if not counts:
                continue
            best = min(counts, key=lambda k: (-counts[k], k))
            if label.get(node) != best:
                label[node] = best
                changed = True
        if not changed:
            break

    # Result = LLM seed memberships (multi) ∪ propagated community labels.
    result: dict[str, set[str]] = {key: set(members) for key, members in seed_members.items()}
    for node, key in label.items():
        result.setdefault(key, set()).add(node)
    return result
