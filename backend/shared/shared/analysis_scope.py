"""Which files are outside the *learning* scope (boilerplate with no implementation to study).

Single source of truth shared by the learning-plan generator (which skips these files) and the galaxy
projection (which labels them 対象外 / ``out_of_scope`` instead of 未着手 / ``unexplored``). ``__init__.py``
and ``__main__.py`` are package markers / re-exports — there is nothing to learn or quiz on them, so
they should not appear as an un-started understanding gap on the map.
"""

NON_LEARNABLE_BASENAMES = frozenset({"__init__.py", "__main__.py"})


def is_learnable_path(path: str) -> bool:
    """Whether ``path`` is a learning target (``False`` for package-marker boilerplate)."""
    return path.rsplit("/", 1)[-1] not in NON_LEARNABLE_BASENAMES
