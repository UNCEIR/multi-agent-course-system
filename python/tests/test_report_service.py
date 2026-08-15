# -*- coding: utf-8 -*-
"""report 服务层测试：四决策点 prompt、token 下载、分类规则兜底。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.report.service import make_download_url, verify_download_token
from tools.report.render_report_batch import classify_by_rules


# ── 分类规则兜底 ───────────────────────────────────────────────────────
@pytest.mark.unit
def test_classify_rules_daofa():
    assert classify_by_rules({"files": [{"has_daofa": True, "has_required_optional": False}]}) == 2


@pytest.mark.unit
def test_classify_rules_required_optional():
    assert classify_by_rules({"files": [{"has_daofa": False, "has_required_optional": True}]}) == 1


@pytest.mark.unit
def test_classify_rules_ambiguous():
    assert classify_by_rules({"files": [{"has_daofa": False, "has_required_optional": False}]}) is None
    assert classify_by_rules({"files": []}) is None


# ── token 下载 ─────────────────────────────────────────────────────────
def _settings(**kw):
    s = MagicMock()
    s.report_download_secret = "test-secret"
    s.report_download_ttl_hours = 24
    for k, v in kw.items():
        setattr(s, k, v)
    return s


@pytest.mark.unit
def test_download_token_roundtrip():
    with patch("config.get_settings", return_value=_settings()):
        url = make_download_url("b1/s1.pdf")
        assert "/api/v1/report/download" in url
        file_key = url.split("file_key=")[1].split("&")[0]
        token = url.split("token=")[1].split("&")[0]
        exp = int(url.split("expires_at=")[1])
        assert verify_download_token(file_key, token, exp) is None


@pytest.mark.unit
def test_download_token_tampered():
    with patch("config.get_settings", return_value=_settings()):
        url = make_download_url("b1/s1.pdf")
        token = url.split("token=")[1].split("&")[0]
        exp = int(url.split("expires_at=")[1])
        assert verify_download_token("b1/OTHER.pdf", token, exp) == "invalid_token"


@pytest.mark.unit
def test_download_token_expired():
    with patch("config.get_settings", return_value=_settings()):
        url = make_download_url("b1/s1.pdf")
        token = url.split("token=")[1].split("&")[0]
        assert verify_download_token("b1/s1.pdf", token, 0) == "token_expired"


@pytest.mark.unit
def test_download_disabled_without_secret():
    with patch("config.get_settings", return_value=_settings(report_download_secret="")):
        assert verify_download_token("b1/s1.pdf", "x", 9999999999) == "download_disabled"
