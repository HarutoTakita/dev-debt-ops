"""Tests for seeded label propagation (feature graph-community re-alignment, issue 293)."""

from service.services.feature_communities import assign_communities


def test_propagates_seed_along_edges() -> None:
    # auth seeds a.py; b.py and c.py are graph-connected → they join auth's community.
    result = assign_communities(
        {"auth": {"a.py"}},
        [("a.py", "b.py"), ("b.py", "c.py")],
        {"a.py", "b.py", "c.py"},
    )
    assert result["auth"] == {"a.py", "b.py", "c.py"}


def test_disconnected_component_keeps_its_own_seed() -> None:
    # Two disjoint graph components, each with its own seed → each grows independently.
    result = assign_communities(
        {"auth": {"a.py"}, "billing": {"x.py"}},
        [("a.py", "b.py"), ("x.py", "y.py")],
        {"a.py", "b.py", "x.py", "y.py"},
    )
    assert result["auth"] == {"a.py", "b.py"}
    assert result["billing"] == {"x.py", "y.py"}


def test_isolated_unseeded_file_is_not_assigned() -> None:
    # loner.py has no edge and no seed → propagation can't reach it; it joins no feature.
    result = assign_communities({"auth": {"a.py"}}, [("a.py", "b.py")], {"a.py", "b.py", "loner.py"})
    assert "loner.py" not in result["auth"]
    assert all("loner.py" not in members for members in result.values())


def test_preserves_multi_membership_seeds() -> None:
    # a.py is seeded into BOTH features → it stays in both (multi-membership preserved).
    result = assign_communities(
        {"auth": {"a.py"}, "billing": {"a.py", "d.py"}},
        [],
        {"a.py", "d.py"},
    )
    assert "a.py" in result["auth"]
    assert "a.py" in result["billing"]
    assert "d.py" in result["billing"]


def test_tie_breaks_deterministically_by_smallest_key() -> None:
    # mid.py neighbors one auth file and one billing file (a tie) → smallest key "auth" wins.
    result = assign_communities(
        {"auth": {"a.py"}, "billing": {"b.py"}},
        [("a.py", "mid.py"), ("b.py", "mid.py")],
        {"a.py", "b.py", "mid.py"},
    )
    assert "mid.py" in result["auth"]
    assert "mid.py" not in result["billing"]


def test_drops_paths_outside_valid_set() -> None:
    # Seeds and edge endpoints not in valid_paths are ignored.
    result = assign_communities(
        {"auth": {"a.py", "ghost.py"}},
        [("a.py", "b.py"), ("a.py", "ghost.py")],
        {"a.py", "b.py"},
    )
    assert result["auth"] == {"a.py", "b.py"}
