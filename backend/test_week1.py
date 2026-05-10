"""Smoke test for tree-sitter language parsers (Week 1)."""
import sys


try:
    from tree_sitter import Language, Parser
    import tree_sitter_python as tspython
    import tree_sitter_javascript as tsjavascript
    import tree_sitter_typescript as tstypescript
    import networkx as nx
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    sys.exit(1)


py_lang  = Language(tspython.language(), "python")
js_lang  = Language(tsjavascript.language(), "javascript")
ts_lang  = Language(tstypescript.language_typescript(), "typescript")
tsx_lang = Language(tstypescript.language_tsx(), "tsx")

py_parser  = Parser(); py_parser.set_language(py_lang)
js_parser  = Parser(); js_parser.set_language(js_lang)
ts_parser  = Parser(); ts_parser.set_language(ts_lang)
tsx_parser = Parser(); tsx_parser.set_language(tsx_lang)


py_code = b"def hello(name: str) -> str:\n    return 'Hello ' + name\n"
tree = py_parser.parse(py_code)
assert tree.root_node.type == "module", f"Expected module, got {tree.root_node.type}"
print("OK  Python parse:", tree.root_node.type)


js_code = b"function greet(name) { return name.toUpperCase(); }"
tree_js = js_parser.parse(js_code)
assert tree_js.root_node.type == "program", f"Expected program, got {tree_js.root_node.type}"
print("OK  JS parse:", tree_js.root_node.type)


ts_code = b"function add(a: number, b: number): number { return a + b; }"
tree_ts = ts_parser.parse(ts_code)
assert tree_ts.root_node.type == "program"
print("OK  TS parse:", tree_ts.root_node.type)


g = nx.DiGraph()
g.add_node("a"); g.add_node("b"); g.add_edge("a", "b", edge_type="call")
assert list(g.nodes()) == ["a", "b"]
assert g.number_of_edges() == 1
print("OK  NetworkX DiGraph:", g.number_of_nodes(), "nodes,", g.number_of_edges(), "edges")


sys.path.insert(0, ".")
from core.parser.tree_sitter_parser import TreeSitterParser, FunctionNode

parser = TreeSitterParser()

py_src = (
    "class Greeter:\n"
    "    def greet(self, name: str) -> str:\n"
    '        """Say hello."""\n'
    "        return self._fmt(name)\n"
    "\n"
    "    def _fmt(self, s):\n"
    "        return s.upper()\n"
)
nodes = parser.parse_file("test.py", py_src, "python")
assert len(nodes) == 2, f"Expected 2 function nodes, got {len(nodes)}: {[n.name for n in nodes]}"
assert nodes[0].name == "Greeter.greet"
assert nodes[0].return_type == "str"
assert "greet" in nodes[0].docstring or "hello" in nodes[0].docstring
assert "_fmt" in nodes[0].calls_to, f"calls_to={nodes[0].calls_to}"
assert nodes[0].complexity >= 1
print("OK  Python FunctionNode extraction:", [n.name for n in nodes])


js_src = (
    "class MyService {\n"
    "  fetchData(url) {\n"
    "    const result = httpGet(url);\n"
    "    if (result.ok) { return result.json(); }\n"
    "    return null;\n"
    "  }\n"
    "}\n"
)
js_nodes = parser.parse_file("service.js", js_src, "javascript")
assert len(js_nodes) >= 1, f"Expected >=1 JS node, got {len(js_nodes)}"
method = js_nodes[0]
assert "fetchData" in method.name, f"Got name={method.name}"
assert method.complexity >= 2, f"Expected complexity>=2, got {method.complexity}"
print("OK  JS FunctionNode extraction:", [n.name for n in js_nodes])


from core.parser.call_graph_builder import build_call_graph, graph_to_json, graph_to_pyg_data

all_nodes = nodes + js_nodes
graph = build_call_graph(all_nodes)
assert graph.number_of_nodes() == len(all_nodes)
print("OK  Call graph:", graph.number_of_nodes(), "nodes,", graph.number_of_edges(), "edges")

gj = graph_to_json(graph)
assert "nodes" in gj and "edges" in gj and "stats" in gj
print("OK  graph_to_json stats:", gj["stats"])

pyg = graph_to_pyg_data(graph)
assert "node_ids" in pyg and "edge_index" in pyg and "node_features" in pyg
assert len(pyg["node_ids"]) == len(all_nodes)
print("OK  graph_to_pyg_data node_ids:", len(pyg["node_ids"]))


from core.parser.node_features import Vocabulary, tokenize_name, extract_node_features

assert tokenize_name("parseJsonResponse") == ["parse", "json", "response"]
assert tokenize_name("parse_json_response") == ["parse", "json", "response"]
assert tokenize_name("APIRouter") == ["api", "router"]
print("OK  tokenize_name:", tokenize_name("parseJsonResponse"))

vocab = Vocabulary()
vocab.build_from_nodes(all_nodes)
assert len(vocab) > 2
print("OK  Vocabulary size:", len(vocab))

feats = extract_node_features(nodes[0], vocab)
assert feats["param_count"] == 2  
assert feats["has_docstring"] == 1
assert len(feats["token_ids"]) == 64
print("OK  Node features:", {k: v for k, v in feats.items() if k != "token_ids"})

print()
print("=" * 50)
print("ALL SMOKE TESTS PASSED")
print("=" * 50)
