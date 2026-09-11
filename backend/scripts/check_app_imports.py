# -*- coding: utf-8 -*-
"""Verify that every ``from app.X import name`` inside the app package resolves.

Catches the exact failure class that took down production on 2026-09-04:
``from app.core.config import settings`` where ``settings`` does not exist in
the module (only ``class Settings`` + ``get_settings()`` are defined).

This runs BEFORE deployment so bad code never reaches the server.
"""

import ast
import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent  # backend/
APP = ROOT / "app"
errors: list[str] = []
checked = 0


def collect_py_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for p in APP.rglob("*.py"):
        if "__pycache__" in p.parts or p.name.startswith("_"):
            continue
        files.append(p)
    return files


def check_file(py: pathlib.Path) -> None:
    global checked
    try:
        tree = ast.parse(py.read_text(encoding="utf-8-sig"))
    except SyntaxError as e:
        errors.append(f"{py.relative_to(ROOT)}: 语法错误 {e}")
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        mod = node.module or ""
        if not mod.startswith("app."):
            continue
        # Locate the target package directory to distinguish sub-module imports
        # (e.g. ``from app.pilot import readiness`` where readiness is a module).
        target_dir = APP.joinpath(*mod.split(".")[1:])
        try:
            target = importlib.import_module(mod)
        except Exception as e:  # noqa: BLE001 - collect all import failures
            errors.append(f"{py.relative_to(ROOT)}: 无法导入模块 {mod}: {type(e).__name__}: {e}")
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            sub_mod_file = target_dir / f"{alias.name}.py"
            sub_mod_pkg = target_dir / alias.name / "__init__.py"
            if sub_mod_file.exists() or sub_mod_pkg.exists():
                continue  # valid sub-module import
            if not hasattr(target, alias.name):
                errors.append(
                    f"{py.relative_to(ROOT)}: {mod} 中没有名称 {alias.name}"
                )
    checked += 1


def main() -> int:
    for py in collect_py_files():
        check_file(py)
    if errors:
        print(f"FAIL: {len(errors)} 个 app 内部导入问题:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"OK: app 内部导入完整性检查通过（{checked} 个文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
