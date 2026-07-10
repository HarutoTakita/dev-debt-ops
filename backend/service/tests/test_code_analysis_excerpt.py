"""Unit tests for the implementation-excerpt helpers (skip leading docstring / imports / comments).

These back the quiz material + code-snippet selection: a docstring-heavy file must not yield an
excerpt that is pure module docstring + imports (natural-language prose instead of implementation).
"""

from service.services import code_analysis


def test_skips_module_docstring_and_imports() -> None:
    content = '"""Module doc.\n\nMore doc.\n"""\nimport os\nfrom x import y\n\ndef f():\n    return 1\n'
    assert code_analysis.leading_code_line(content) == 8  # the `def f():` line
    assert code_analysis.implementation_excerpt(content).startswith("def f():")


def test_skips_line_comments() -> None:
    content = "# a comment\n// c comment\nx = 1\n"
    assert code_analysis.implementation_excerpt(content).startswith("x = 1")


def test_single_line_docstring_then_code() -> None:
    content = '"""one line."""\nimport os\ncode = 2\n'
    assert code_analysis.implementation_excerpt(content).startswith("code = 2")


def test_block_comment_skipped() -> None:
    content = "/* license\n block */\nconst a = 1;\n"
    assert code_analysis.implementation_excerpt(content).startswith("const a = 1;")


def test_no_boilerplate_returns_original() -> None:
    content = "def f():\n    return 1\n"
    assert code_analysis.leading_code_line(content) == 1
    assert code_analysis.implementation_excerpt(content) == content


def test_all_boilerplate_returns_from_top() -> None:
    """A file that is only docstring + imports has no 'real code' → show from the top, never empty."""
    content = '"""only docstring."""\nimport os\n'
    assert code_analysis.leading_code_line(content) == 1
    assert code_analysis.implementation_excerpt(content) == content


def test_prefixed_docstring_delimiter() -> None:
    content = 'r"""raw doc\nline"""\nvalue = 3\n'
    assert code_analysis.implementation_excerpt(content).startswith("value = 3")
