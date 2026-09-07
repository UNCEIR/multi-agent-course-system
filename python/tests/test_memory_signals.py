# -*- coding: utf-8 -*-
"""本地信号预筛纯函数测试（B 方案：强改口组 / 弱披露组）。"""

from __future__ import annotations

import pytest

from agent.memory.signals import has_disclosure_signal, has_retraction_signal


@pytest.mark.unit
def test_retraction_hits():
    for t in [
        "我不再喜欢运动了",
        "我以后不打篮球了",
        "我改主意了，不选这门课",
        "我决定不参加运动会",
        "我不喜欢运动了",
        "我不爱打篮球了",
    ]:
        assert has_retraction_signal(t), t


@pytest.mark.unit
def test_retraction_misses():
    for t in ["今天天气不错", "帮我推荐课程", "你好", "哈哈", "这门课作业多吗"]:
        assert not has_retraction_signal(t), t


@pytest.mark.unit
def test_disclosure_group():
    assert has_disclosure_signal("我很喜欢打篮球")
    assert has_disclosure_signal("我是广东工业大学大二学生")
    assert not has_disclosure_signal("今天天气不错")
