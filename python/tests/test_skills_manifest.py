# -*- coding: utf-8 -*-
"""skills manifest 加载期校验（Phase 4 D9，对齐 deepagents SkillsMiddleware 要求）。

断言每个 python/skills/*/SKILL.md 的 frontmatter 满足渐进式加载前置：
- name / description 必填
- description ≤ 1024 字符（deepagents MAX_SKILL_DESCRIPTION_LENGTH）
- description 建议含「何时用/何时不用」意图消歧信号（warning 计数，不 fail）
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
FRONTMATTER_RE = re.compile(r"^---\s*$(.*?)^---\s*$", re.MULTILINE | re.DOTALL)
MAX_DESC = 1024


def _parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.search(text)
    if not m:
        return {}
    data = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip()
    return data


def _skills() -> list[tuple[str, Path, dict]]:
    items = []
    for p in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        meta = _parse_frontmatter(p.read_text(encoding="utf-8"))
        items.append((p.parent.name, p, meta))
    return items


@pytest.mark.unit
def test_skills_exist():
    skills = _skills()
    assert len(skills) >= 5, "skills 目录应有多个技能"


@pytest.mark.unit
def test_every_skill_has_name_and_description():
    for name, path, meta in _skills():
        assert meta.get("name"), f"{path}: 缺 name"
        assert meta.get("description"), f"{path}: 缺 description"
        assert meta["name"] == name, f"{path}: frontmatter name 与目录名不一致"


@pytest.mark.unit
def test_description_within_1024_chars():
    for name, path, meta in _skills():
        desc = meta.get("description", "")
        assert len(desc) <= MAX_DESC, f"{path}: description {len(desc)} > {MAX_DESC}"


@pytest.mark.unit
def test_description_intent_signals_warning():
    """description 含「何时用/何时不用」消歧信号（Phase 4 D9：warning 级，不阻断）。"""
    missing = []
    for name, path, meta in _skills():
        desc = meta.get("description", "")
        if not any(s in desc for s in ("何时用", "何时不用", "边界", "不要", "请用")):
            missing.append(name)
    # 不强 fail（既有技能可能未达模板），但要求 ≤2 个未达标，推动补 description
    assert len(missing) <= 2, f"description 缺意图消歧信号: {missing}"
