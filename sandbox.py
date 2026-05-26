import ast

ALLOWED_MODULES = frozenset({
    "runner.koan",
    "re",
    "random",
    "functools",
    "unittest",
    "collections",
    "string",
    "math",
    "itertools",
    "copy",
    "typing",
})

BLOCKED_BUILTINS = frozenset({
    "eval", "exec", "compile",
    "__import__",
    "breakpoint",
    "exit", "quit",
    "memoryview",
    "help", "input",
    "globals", "locals", "vars",
    "open",
})

BLOCKED_ATTRS = frozenset({
    "__subclasses__",
    "__globals__",
    "__builtins__",
    "__code__",
    "__func__",
    "__import__",
    "gi_frame",
    "f_globals",
    "f_builtins",
    "f_locals",
})

BLOCKED_NAMES = frozenset({
    "__builtins__",
    "__loader__",
    "__spec__",
})

GUARDED_CALLABLES = frozenset({
    "getattr", "setattr", "delattr",
})

BLOCKED_STRING_KEYS = frozenset({
    "__import__",
    "__builtins__",
    "__globals__",
    "__subclasses__",
    "__code__",
    "__func__",
    "f_globals",
    "f_builtins",
    "f_locals",
})


class _Checker(ast.NodeVisitor):
    def __init__(self):
        self.violations: list[str] = []

    def _add(self, node: ast.AST, msg: str):
        line = getattr(node, "lineno", "?")
        self.violations.append(f"line {line}: {msg}")

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            top = alias.name.split(".")[0]
            if alias.name not in ALLOWED_MODULES and top not in ALLOWED_MODULES:
                self._add(node, f"import '{alias.name}' is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.level > 0:
            self.generic_visit(node)
            return
        module = node.module or ""
        top = module.split(".")[0]
        if module not in ALLOWED_MODULES and top not in ALLOWED_MODULES:
            self._add(node, f"import from '{module}' is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id in BLOCKED_NAMES:
            self._add(node, f"access to '{node.id}' is not allowed")
        if node.id in BLOCKED_BUILTINS:
            self._add(node, f"reference to '{node.id}' is not allowed")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        if isinstance(node.value, ast.Name) and node.value.id in GUARDED_CALLABLES:
            self._add(node, f"aliasing '{node.value.id}' is not allowed")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_BUILTINS:
            self._add(node, f"call to '{node.func.id}()' is not allowed")
        if isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if len(node.args) >= 2:
                arg = node.args[1]
                if isinstance(arg, ast.Constant):
                    val = arg.value
                    if isinstance(val, str) and (val in BLOCKED_ATTRS or val in BLOCKED_BUILTINS):
                        self._add(node, f"getattr access to '{val}' is not allowed")
                elif not isinstance(arg, ast.Constant):
                    self._add(node, "getattr with dynamic attribute name is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in BLOCKED_ATTRS:
            self._add(node, f"access to '{node.attr}' is not allowed")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript):
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            if node.slice.value in BLOCKED_STRING_KEYS:
                self._add(node, f"subscript access to '{node.slice.value}' is not allowed")
        self.generic_visit(node)


def check_code(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"Syntax error: {e.msg} (line {e.lineno})"]

    checker = _Checker()
    checker.visit(tree)
    return checker.violations
