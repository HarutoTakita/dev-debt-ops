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


# --- complexity hotspot / nearest definition / duplicate report ------------


def test_complexity_hotspot_locates_dense_region_not_imports() -> None:
    content = (
        "import os\nimport sys\n\ndef trivial():\n    return 1\n"
        + "\n" * 4
        + "def busy(x):\n"
        + "\n".join(f"    if x == {i} and x or x: pass" for i in range(9))
        + "\n"
    )
    hs = code_analysis.complexity_hotspot(content, "python")
    assert hs is not None
    start, _end, text = hs
    assert "if x ==" in text  # the dense branching region
    assert "import os" not in text  # not the file top
    assert start > 3


def test_complexity_hotspot_none_when_flat() -> None:
    content = "\n".join(f"x{i} = {i}" for i in range(30)) + "\n"  # no decision points anywhere
    assert code_analysis.complexity_hotspot(content, "python") is None


def test_nearest_definition_python_and_js() -> None:
    py = "import os\n\ndef outer():\n    x = 1\n    if x:\n        pass\n"
    assert code_analysis.nearest_definition(py, 5, "python") == "outer"
    js = "const a = 1;\nexport function handler(req) {\n  if (req) return 1;\n}\n"
    assert code_analysis.nearest_definition(js, 3, "ts_js") == "handler"
    assert code_analysis.nearest_definition("x = 1\ny = 2\n", 2, "python") is None


def test_duplicate_report_records_partner_files_and_block() -> None:
    block = "\n".join(f"row{i} = handle({i})" for i in range(8))  # 8 identical lines
    files = {
        "a.py": "import os\n" + block + "\nend_a = 1\n",
        "b.py": "import sys\n" + block + "\nend_b = 2\n",
        "c.py": "z = 0\n",  # unrelated, no duplication
    }
    report = code_analysis.duplicate_report(files)
    a = report["a.py"]
    assert a.ratio > 0
    assert "b.py" in a.related_files  # the cross-file partner is recorded
    assert "row0 = handle(0)" in a.block_text  # verbatim duplicated block, not the file top
    assert a.block_start_line >= 2  # past the `import os` line
    assert report["c.py"].related_files == []
    # find_duplicate_ratios stays a thin ratio-only view over the same computation.
    assert code_analysis.find_duplicate_ratios(files)["a.py"] == a.ratio
