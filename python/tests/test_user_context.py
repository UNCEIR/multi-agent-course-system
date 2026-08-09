# -*- coding: utf-8 -*-
"""用户上下文注入基座测试。"""

from __future__ import annotations

import pytest

from agent.main.context import (
    ANONYMOUS_USER,
    get_current_user_id,
    is_authenticated,
    user_context,
)


def test_default_anonymous():
    assert get_current_user_id() == ANONYMOUS_USER
    assert is_authenticated() is False


def test_user_context_sets_and_restores():
    with user_context("u123"):
        assert get_current_user_id() == "u123"
        assert is_authenticated() is True
    # 退出后还原为匿名
    assert get_current_user_id() == ANONYMOUS_USER


def test_nested_user_context():
    with user_context("outer"):
        with user_context("inner"):
            assert get_current_user_id() == "inner"
        assert get_current_user_id() == "outer"


def test_empty_user_id_treated_anonymous():
    with user_context(""):
        assert get_current_user_id() == ANONYMOUS_USER
        assert is_authenticated() is False
