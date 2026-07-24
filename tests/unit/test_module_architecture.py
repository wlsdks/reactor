from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "reactor"
MODULE_REVIEW = ROOT / "docs" / "migration" / "module-architecture-review.md"

REQUIRED_PACKAGES = {
    "a2a",
    "admin",
    "agents",
    "api",
    "api/routers",
    "api/schemas",
    "artifacts",
    "auth",
    "cache",
    "context",
    "core",
    "evals",
    "guards",
    "hooks",
    "jobs",
    "kernel",
    "mcp",
    "memory",
    "migration",
    "observability",
    "persistence",
    "persistence/repositories",
    "prompt_lab",
    "prompts",
    "providers",
    "rag",
    "response",
    "runtime_settings",
    "runs",
    "sandbox",
    "scheduler",
    "slack",
    "tools",
    "tools/mcp",
    "workers",
}

LANGGRAPH_ALLOWED_PREFIXES = {
    "src/reactor/agents/",
    "src/reactor/memory/",
}

FASTAPI_ALLOWED_PREFIXES = {
    "src/reactor/api/",
}

SQLALCHEMY_ALLOWED_PREFIXES = {
    "src/reactor/core/",
    "src/reactor/persistence/",
}

FORBIDDEN_LANGCHAIN_DESERIALIZATION_IMPORTS = {
    "langchain_core": {"load"},
    "langchain_core.load": {"load", "loads"},
    "langchain_core.load.load": {"load", "loads"},
    "langchain_core.prompts": {"load_prompt"},
    "langchain_core.prompts.loading": {"load_prompt"},
    "langchain.chains.loading": {"load_chain"},
    "langchain.agents.loading": {"load_agent"},
}


def test_required_migration_packages_exist() -> None:
    missing = [
        package
        for package in sorted(REQUIRED_PACKAGES)
        if not (SRC / package / "__init__.py").exists()
    ]

    assert missing == []


def test_framework_imports_stay_behind_boundaries() -> None:
    violations: list[str] = []
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        imports = imported_roots(path)

        if "langgraph" in imports and not has_allowed_prefix(relative, LANGGRAPH_ALLOWED_PREFIXES):
            violations.append(f"{relative}: langgraph import outside agents/memory boundary")
        if "fastapi" in imports and not has_allowed_prefix(relative, FASTAPI_ALLOWED_PREFIXES):
            violations.append(f"{relative}: fastapi import outside api boundary")
        sqlalchemy_outside_boundary = "sqlalchemy" in imports and not has_allowed_prefix(
            relative,
            SQLALCHEMY_ALLOWED_PREFIXES,
        )
        if sqlalchemy_outside_boundary:
            violations.append(f"{relative}: sqlalchemy import outside core/persistence boundary")

    assert violations == []


def test_runtime_security_invariants_have_static_sensors() -> None:
    violations: list[str] = []
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        imports = imported_modules(path)

        if any(name.startswith("langgraph.checkpoint.sqlite") for name in imports):
            violations.append(f"{relative}: sqlite checkpointer import is forbidden")
        if "pickle" in imports:
            violations.append(f"{relative}: pickle import is forbidden")
        violations.extend(unsafe_langchain_deserialization_violations(path, relative=relative))
        if "LANGGRAPH_STRICT_MSGPACK" in source and relative != "src/reactor/__init__.py":
            violations.append(f"{relative}: strict msgpack bootstrap belongs in reactor.__init__")

    init_source = (SRC / "__init__.py").read_text(encoding="utf-8")
    assert 'os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")' in init_source
    assert "langgraph" not in imported_roots(SRC / "__init__.py")
    assert violations == []


def test_langchain_deserialization_sensor_flags_unsafe_load_imports(tmp_path: Path) -> None:
    unsafe_module = tmp_path / "unsafe.py"
    unsafe_module.write_text(
        "\n".join(
            [
                "import importlib",
                "from importlib import import_module",
                "import langchain_core.load as lc_load",
                "import langchain_core.load.load as lc_load_impl",
                "import langchain.chains.loading",
                'load_module_dynamic = import_module("langchain_core.load")',
                'load_impl_dynamic = importlib.import_module("langchain_core.load.load")',
                'load_builtin_dynamic = __import__("langchain_core.load", fromlist=["loads"])',
                "from langchain_core import load as load_module",
                "from langchain_core.load import load",
                "from langchain_core.load import loads as revive_json",
                "from langchain_core.load.load import loads",
                "from langchain_core.prompts import load_prompt",
                "from langchain_core.prompts.loading import load_prompt as load_prompt_impl",
            ]
        ),
        encoding="utf-8",
    )

    assert unsafe_langchain_deserialization_violations(
        unsafe_module,
        relative="src/reactor/prompts/unsafe.py",
    ) == [
        "src/reactor/prompts/unsafe.py: langchain_core.load module import is forbidden",
        "src/reactor/prompts/unsafe.py: langchain_core.load.load module import is forbidden",
        "src/reactor/prompts/unsafe.py: langchain.chains.loading module import is forbidden",
        "src/reactor/prompts/unsafe.py: langchain_core.load import is forbidden",
        "src/reactor/prompts/unsafe.py: langchain_core.load.load import is forbidden",
        "src/reactor/prompts/unsafe.py: langchain_core.load.loads import is forbidden",
        "src/reactor/prompts/unsafe.py: langchain_core.load.load.loads import is forbidden",
        "src/reactor/prompts/unsafe.py: langchain_core.prompts.load_prompt import is forbidden",
        "src/reactor/prompts/unsafe.py: "
        "langchain_core.prompts.loading.load_prompt import is forbidden",
        "src/reactor/prompts/unsafe.py: langchain_core.load dynamic import is forbidden",
        "src/reactor/prompts/unsafe.py: langchain_core.load.load dynamic import is forbidden",
        "src/reactor/prompts/unsafe.py: langchain_core.load dynamic import is forbidden",
    ]


def test_dynamic_import_sensor_rejects_nonliteral_targets(tmp_path: Path) -> None:
    unsafe_module = tmp_path / "unsafe_dynamic.py"
    unsafe_module.write_text(
        "\n".join(
            [
                "import importlib",
                "from importlib import import_module",
                "def import_from_user(module_name: str):",
                "    import_module(module_name)",
                "    importlib.import_module(module_name)",
                "    __import__(module_name)",
            ]
        ),
        encoding="utf-8",
    )

    assert unsafe_langchain_deserialization_violations(
        unsafe_module,
        relative="src/reactor/providers/unsafe_dynamic.py",
    ) == [
        "src/reactor/providers/unsafe_dynamic.py: dynamic import target must be literal",
        "src/reactor/providers/unsafe_dynamic.py: dynamic import target must be literal",
        "src/reactor/providers/unsafe_dynamic.py: dynamic import target must be literal",
    ]


def test_module_architecture_review_does_not_call_implemented_packages_scaffolds() -> None:
    scaffold_packages = scaffold_packages_from_module_review(MODULE_REVIEW.read_text())
    stale_scaffolds = [
        package for package in sorted(scaffold_packages) if non_init_python_files(SRC / package)
    ]

    assert stale_scaffolds == []


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def unsafe_langchain_deserialization_violations(path: Path, *, relative: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_LANGCHAIN_DESERIALIZATION_IMPORTS:
                    violations.append(f"{relative}: {alias.name} module import is forbidden")
            continue
        if isinstance(node, ast.Call):
            is_dynamic_import, dynamic_module = dynamic_import_call_target(node)
            if is_dynamic_import and dynamic_module is None:
                violations.append(f"{relative}: dynamic import target must be literal")
            elif dynamic_module in FORBIDDEN_LANGCHAIN_DESERIALIZATION_IMPORTS:
                violations.append(f"{relative}: {dynamic_module} dynamic import is forbidden")
            continue
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        forbidden_names = FORBIDDEN_LANGCHAIN_DESERIALIZATION_IMPORTS.get(node.module)
        if not forbidden_names:
            continue
        for alias in node.names:
            if alias.name in forbidden_names:
                violations.append(f"{relative}: {node.module}.{alias.name} import is forbidden")
    return violations


def dynamic_import_call_target(node: ast.Call) -> tuple[bool, str | None]:
    function = node.func
    direct_import_module = isinstance(function, ast.Name) and function.id == "import_module"
    builtin_import = isinstance(function, ast.Name) and function.id == "__import__"
    attribute_import_module = (
        isinstance(function, ast.Attribute)
        and isinstance(function.value, ast.Name)
        and function.value.id == "importlib"
        and function.attr == "import_module"
    )
    if not (direct_import_module or attribute_import_module or builtin_import):
        return False, None
    if not node.args:
        return True, None
    first_arg = node.args[0]
    if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
        return True, None
    return True, first_arg.value


def has_allowed_prefix(relative_path: str, prefixes: set[str]) -> bool:
    return any(relative_path.startswith(prefix) for prefix in prefixes)


def scaffold_packages_from_module_review(text: str) -> set[str]:
    packages: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("| `") or "Scaffold only" not in line:
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) < 2:
            continue
        packages.add(parts[0].strip("`"))
    return packages


def non_init_python_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        file
        for file in path.rglob("*.py")
        if file.name != "__init__.py" and "__pycache__" not in file.parts
    )
