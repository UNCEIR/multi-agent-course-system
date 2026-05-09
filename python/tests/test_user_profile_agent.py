"""Unit tests for UserProfileAgent — profile parsing, behavior collection, LLM integration."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.user_profile_agent import UserProfileAgent
from models.schemas import UserProfile, UserProfileResult, UserSegment


class TestUserProfileAgent:
    @pytest.mark.agent
    async def test_parse_profile_valid_json(self):
        """Valid JSON response from LLM is parsed into UserProfile."""
        agent = UserProfileAgent()
        raw = json.dumps({
            "segments": ["active", "high_value"],
            "preferred_categories": ["手机", "耳机"],
            "price_range": [500, 8000],
            "rfm_score": {"recency": 0.85, "frequency": 0.6, "monetary": 0.7},
            "real_time_tags": {"活跃时段": "晚间"},
        })

        profile = agent._parse_profile("user_001", raw)

        assert isinstance(profile, UserProfile)
        assert profile.user_id == "user_001"
        assert UserSegment.ACTIVE in profile.segments
        assert UserSegment.HIGH_VALUE in profile.segments

    @pytest.mark.agent
    async def test_parse_profile_codeblock_json(self):
        """JSON wrapped in markdown code blocks is still parsed correctly."""
        agent = UserProfileAgent()
        raw = '```json\n{"segments":["new_user"],"preferred_categories":["平板"]}\n```'

        profile = agent._parse_profile("user_002", raw)

        assert profile.user_id == "user_002"
        assert UserSegment.NEW_USER in profile.segments

    @pytest.mark.agent
    async def test_parse_profile_invalid_json(self):
        """Invalid JSON falls back to default profile with ACTIVE segment."""
        agent = UserProfileAgent()
        profile = agent._parse_profile("user_003", "not valid json at all")

        assert profile.user_id == "user_003"
        assert profile.segments == [UserSegment.ACTIVE]
        assert profile.preferred_categories == []

    @pytest.mark.agent
    async def test_parse_profile_unknown_segment_ignored(self):
        """Unknown segment values are silently ignored."""
        agent = UserProfileAgent()
        raw = json.dumps({
            "segments": ["active", "unknown_bogus_segment", "high_value"],
        })

        profile = agent._parse_profile("user_004", raw)

        assert len(profile.segments) == 2
        assert UserSegment.ACTIVE in profile.segments
        assert UserSegment.HIGH_VALUE in profile.segments

    @pytest.mark.agent
    async def test_collect_behavior_without_feature_store(self):
        """Without feature store, behavior is collected from context."""
        agent = UserProfileAgent()
        context = {
            "recent_views": ["手表", "键盘"],
            "purchase_count_30d": 5,
        }
        behavior = await agent._collect_behavior("user_005", context)

        assert behavior["user_id"] == "user_005"
        assert behavior["recent_views"] == ["手表", "键盘"]
        assert behavior["purchase_count_30d"] == 5
        # Defaults present
        assert "view_count_7d" in behavior
        assert "recent_purchases" in behavior

    @pytest.mark.agent
    async def test_collect_behavior_defaults(self):
        """With empty context, sensible defaults are used."""
        agent = UserProfileAgent()
        behavior = await agent._collect_behavior("user_006", {})

        assert behavior["user_id"] == "user_006"
        assert behavior["recent_views"] == ["手机", "耳机", "平板"]
        assert behavior["recent_purchases"] == ["充电器"]
        assert behavior["view_count_7d"] == 25

    @pytest.mark.agent
    async def test_selects_default_segment_when_parsing_fails(self):
        """Missing segments field defaults to ACTIVE only."""
        agent = UserProfileAgent()
        raw = json.dumps({"preferred_categories": ["手机"]})

        profile = agent._parse_profile("user_007", raw)

        assert profile.segments == [UserSegment.ACTIVE]

    @pytest.mark.agent
    async def test_result_type_is_user_profile_result(self):
        """execute method returns UserProfileResult with attached profile."""
        agent = UserProfileAgent()
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value.content = json.dumps({
            "segments": ["active"],
            "preferred_categories": ["手机"],
            "price_range": [0, 10000],
            "rfm_score": {"recency": 0.8, "frequency": 0.5, "monetary": 0.6},
            "real_time_tags": {},
        })
        agent.llm = mock_llm

        result = await agent._execute(user_id="user_008", context={})

        assert isinstance(result, UserProfileResult)
        assert result.success is True
        assert result.profile is not None
        assert result.confidence == 0.85
        mock_llm.ainvoke.assert_called_once()
