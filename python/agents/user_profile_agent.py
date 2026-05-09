from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import (
    AgentResult,
    UserProfile,
    UserProfileResult,
    UserSegment,
)

from .base_agent import BaseAgent

SYSTEM_PROMPT = """你是一个电商用户画像分析专家。
根据用户的行为数据,分析用户特征并生成画像。

输出JSON格式:
{
  "segments": ["new_user"|"active"|"high_value"|"price_sensitive"|"churn_risk"],
  "preferred_categories": ["类目1", "类目2"],
  "price_range": [最低价, 最高价],
  "rfm_score": {"recency": 0-1, "frequency": 0-1, "monetary": 0-1},
  "real_time_tags": {"活跃时段": "...", "偏好风格": "...", "品牌偏好": "..."}
}

只输出JSON,不要其他内容。"""


class UserProfileAgent(BaseAgent):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            name="user_profile",
            timeout=settings.agent_timeout_user_profile,
        )
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.3,
            max_tokens=1024,
        )
        self.feature_store: Any = None

    async def _execute(self, **kwargs: Any) -> UserProfileResult:
        user_id: str = kwargs["user_id"]
        context: dict = kwargs.get("context", {})

        behavior_data = await self._collect_behavior(user_id, context)
        profile_data = await self._analyze_profile(user_id, behavior_data)

        return UserProfileResult(
            success=True,
            profile=profile_data,
            data={"raw_behavior": behavior_data},
            confidence=0.85,
        )

    async def _collect_behavior(self, user_id: str, context: dict) -> dict:
        if self.feature_store:
            return await self.feature_store.get_user_features(user_id)
        return {
            "user_id": user_id,
            "recent_views": context.get("recent_views", ["手机", "耳机", "平板"]),
            "recent_purchases": context.get("recent_purchases", ["充电器"]),
            "view_count_7d": context.get("view_count_7d", 25),
            "purchase_count_30d": context.get("purchase_count_30d", 3),
            "avg_order_amount": context.get("avg_order_amount", 299.0),
            "active_hours": context.get("active_hours", [20, 21, 22]),
            "last_purchase_days": context.get("last_purchase_days", 30),
            "device_type": context.get("device_type", "mobile"),
            "favorite_brands": context.get("favorite_brands", []),
            "coupon_usage_rate": context.get("coupon_usage_rate", 0.3),
        }

    async def _analyze_profile(self, user_id: str, behavior_data: dict) -> UserProfile:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"用户ID: {user_id}\n行为数据: {json.dumps(behavior_data, ensure_ascii=False)}"),
        ]
        response = await self.llm.ainvoke(messages)
        data = self._parse_json(response.content)

        segments = []
        for s in data.get("segments", ["active"]):
            try:
                segments.append(UserSegment(s))
            except ValueError:
                continue

        price_range_raw = data.get("price_range", [0, 10000])
        price_range = (
            float(price_range_raw[0]),
            float(price_range_raw[1]) if len(price_range_raw) > 1 else 10000.0,
        )

        return UserProfile(
            user_id=user_id,
            segments=segments or [UserSegment.ACTIVE],
            preferred_categories=data.get("preferred_categories", []),
            price_range=price_range,
            rfm_score=data.get("rfm_score", {}),
            real_time_tags=data.get("real_time_tags", {}),
        )

    def _parse_json(self, raw: str) -> dict:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {}
