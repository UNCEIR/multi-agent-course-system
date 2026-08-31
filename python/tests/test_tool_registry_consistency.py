# -*- coding: utf-8 -*-
"""注册一致性测试：AgentSpec 白名单 ⊆ runtime 实际注册集合。

防止"白名单引用未注册工具"（如 image_generate_get / evaluation 三函数）静默缺失。
通过 AST 解析 agent/runtime.py 提取真实注册清单，避免测试与实现手工重复。
"""

from __future__ import annotations

import ast
from pathlib import Path

from tools.registry import ToolRegistry

RUNTIME_PATH = Path(__file__).resolve().parents[1] / "agent" / "runtime.py"


def _runtime_registered_names() -> list[str]:
    """解析 runtime.py 中 register_many/register 调用的工具标识符名。"""
    tree = ast.parse(RUNTIME_PATH.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr in ("register_many", "register"):
            for arg in node.args:
                if isinstance(arg, ast.List):
                    for elt in arg.elts:
                        if isinstance(elt, ast.Name):
                            names.append(elt.id)
    return names


def _build_registry() -> ToolRegistry:
    import tools

    tool_objs = []
    for name in _runtime_registered_names():
        tool = getattr(tools, name, None)
        assert tool is not None, f"runtime 注册名 {name!r} 不在 tools 包导出中"
        tool_objs.append(tool)
    registry = ToolRegistry()
    registry.register_many(tool_objs)
    return registry


def _registered_name_set(registry: ToolRegistry) -> set[str]:
    return {getattr(t, "name", None) or t.__name__ for t in registry.get_all()}


def test_runtime_registered_names_all_exported():
    assert len(_runtime_registered_names()) >= 20, "runtime 注册清单解析异常（少于 20 个工具）"
    import tools

    missing = [n for n in _runtime_registered_names() if not hasattr(tools, n)]
    assert not missing, f"runtime 注册了 tools 包未导出的名字: {missing}"


def test_all_specs_whitelist_subset_of_registered_tools():
    from agent.main.specs import (
        EVALUATION_AGENT_SPEC,
        MAIN_AGENT_SPEC,
        PPT_AGENT_SPEC,
        RECOMMENDATION_AGENT_SPEC,
        REPORT_AGENT_SPEC,
    )

    registry = _build_registry()
    registered = _registered_name_set(registry)
    specs = [
        MAIN_AGENT_SPEC,
        RECOMMENDATION_AGENT_SPEC,
        REPORT_AGENT_SPEC,
        EVALUATION_AGENT_SPEC,
        PPT_AGENT_SPEC,
    ]
    for spec in specs:
        if not spec.allowed_tools:
            continue
        missing = set(spec.allowed_tools) - registered
        assert not missing, (
            f"{spec.name} 白名单引用了未注册工具: {sorted(missing)}"
            "（请到 agent/runtime.py 的 register_many 补齐注册）"
        )
        available = registry.get_all(allowed=list(spec.allowed_tools))
        assert len(available) == len(spec.allowed_tools)


def test_all_registered_tools_have_args_schema():
    registry = _build_registry()
    for tool in registry.get_all():
        schema = getattr(tool, "args_schema", None)
        assert schema is not None, f"工具 {tool.name} 缺少 args_schema"


def test_evaluation_triple_and_image_get_are_registered():
    registry = _build_registry()
    registered = _registered_name_set(registry)
    assert "image_generate_get" in registered
    for name in ("design_dimensions", "compute_radar_values", "generate_comment"):
        assert name in registered, f"evaluation 工具 {name} 尚未注册"