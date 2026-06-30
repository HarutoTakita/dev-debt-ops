"""issue 250: deterministic source-based function/file graph (CGC-independent L3 fallback)."""

from service.services import function_graph


class TestExtractPython:
    def test_functions_and_intra_file_calls(self) -> None:
        src = "def a():\n    b()\n\ndef b():\n    pass\n"
        defs, calls = function_graph.extract_python(src)
        assert defs == ["a", "b"]
        assert ("a", "b") in calls  # forward reference resolves (filtered after full walk)

    def test_method_calls_resolve_by_attr_name(self) -> None:
        src = "class C:\n    def m(self):\n        self.helper()\n    def helper(self):\n        pass\n"
        defs, calls = function_graph.extract_python(src)
        assert set(defs) == {"m", "helper"}
        assert ("m", "helper") in calls

    def test_external_calls_excluded(self) -> None:
        defs, calls = function_graph.extract_python("def a():\n    print('x')\n")
        assert defs == ["a"]
        assert calls == []  # print is not defined in this file

    def test_syntax_error_is_empty(self) -> None:
        assert function_graph.extract_python("def (:\n") == ([], [])


class TestExtractTsJs:
    def test_declarations_arrows_methods(self) -> None:
        src = (
            "function foo(){}\n"
            "const bar = () => {}\n"
            "export function baz(x){}\n"
            "class A {\n  doThing() {\n    return 1;\n  }\n}\n"
        )
        names, calls = function_graph.extract_ts_js(src)
        assert {"foo", "bar", "baz", "doThing"} <= set(names)
        assert calls == []  # edges left to CGC for TS/JS

    def test_control_keywords_not_captured_as_methods(self) -> None:
        names, _ = function_graph.extract_ts_js("if (x) {\n}\nwhile (y) {\n}\n")
        assert names == []


class TestBuildSnapshot:
    def test_aggregates_functions_calls_and_file_edges(self) -> None:
        files = {
            "app/util.py": "def helper():\n    pass\n",
            "app/main.py": (
                "from app.util import helper\n\ndef run():\n    helper()\n    inner()\n\ndef inner():\n    pass\n"
            ),
        }
        snap = function_graph.build_snapshot(files)
        assert {"file": "app/util.py", "name": "helper"} in snap["functions"]
        assert {"file": "app/main.py", "name": "run"} in snap["functions"]
        # intra-file call (run -> inner, both in main.py); cross-file helper() is NOT a function_call edge
        assert {"file": "app/main.py", "source": "run", "target": "inner"} in snap["function_calls"]
        # file_edges from the import graph (main imports util)
        assert {"source": "app/main.py", "target": "app/util.py"} in snap["file_edges"]

    def test_ts_file_yields_nodes(self) -> None:
        snap = function_graph.build_snapshot({"web/app.ts": "export function boot(){}\n"})
        assert {"file": "web/app.ts", "name": "boot"} in snap["functions"]

    def test_empty_when_no_source(self) -> None:
        assert function_graph.build_snapshot({}) == {}
        assert function_graph.build_snapshot({"README.md": "# hi\n", "data.json": "{}"}) == {}
