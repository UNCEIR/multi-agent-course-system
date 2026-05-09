"""
内容个性化Agent — 个性化页面布局与内容推荐
- 首页布局：根据用户画像动态调整模块排列
- Banner推荐：匹配用户兴趣的首屏大图
- 频道排序：用户偏好类目优先展示
- 内容策略：新人引导 vs 老客留存 vs VIP尊享
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import ContentPersonalizationResult, UserProfile, UserSegment

from .base_agent import BaseAgent

LAYOUT_PROMPT = """你是电商页面个性化设计专家。根据用户画像设计个性化首页布局。

用户画像:
- 用户ID: {user_id}
- 分群: {segments}
- 偏好类目: {categories}
- 价格区间: {price_range}
- RFM评分: {rfm}

场景: {scene}

请输出JSON布局配置:
{{
  "layout_type": "new_user_welcome|active_discover|vip_exclusive|churn_retention",
  "modules": [
    {{"type": "banner|category_grid|flash_sale|recommendation|live_stream|brand_zone", "title": "模块标题", "priority": 1-5, "config": {{}}}}
  ],
  "theme": "色彩主题",
  "banner_strategy": "首屏Banner策略",
  "discount_display": "价格展示策略",
  "personalization_factors": {{"factor1": "说明"}}
}}
只输出JSON。"""

MODULE_TEMPLATES = {
    UserSegment.NEW_USER: {
        "layout_type": "new_user_welcome",
        "modules": [
            {"type": "banner", "title": "新人专享福利", "priority": 1, "config": {"style": "welcome_pack"}},
            {"type": "category_grid", "title": "热门品类探索", "priority": 2, "config": {"categories": "top"}},
            {"type": "flash_sale", "title": "限时新人价", "priority": 3, "config": {"discount": "50%", "time_limited": True}},
            {"type": "recommendation", "title": "猜你喜欢", "priority": 4, "config": {"algo": "new_user_cf"}},
            {"type": "live_stream", "title": "正在直播", "priority": 5, "config": {"auto_play": False}},
        ],
        "theme": "vibrant_orange",
        "banner_strategy": "新人专享大礼包",
        "discount_display": "突出首单优惠",
    },
    UserSegment.HIGH_VALUE: {
        "layout_type": "vip_exclusive",
        "modules": [
            {"type": "banner", "title": "VIP尊享新品首发", "priority": 1, "config": {"style": "premium"}},
            {"type": "brand_zone", "title": "品牌专区", "priority": 2, "config": {"brands": "premium"}},
            {"type": "recommendation", "title": "为您臻选", "priority": 3, "config": {"algo": "vip_personalized"}},
            {"type": "live_stream", "title": "专属直播间", "priority": 4, "config": {"vip_only": True}},
            {"type": "category_grid", "title": "探索更多", "priority": 5, "config": {"categories": "all"}},
        ],
        "theme": "elegant_black",
        "banner_strategy": "高端品牌联名",
        "discount_display": "会员专属价",
    },
    UserSegment.PRICE_SENSITIVE: {
        "layout_type": "value_seeking",
        "modules": [
            {"type": "flash_sale", "title": "限时抢购", "priority": 1, "config": {"discount": "max", "countdown": True}},
            {"type": "banner", "title": "今日特价", "priority": 2, "config": {"style": "deal"}},
            {"type": "recommendation", "title": "超值好物", "priority": 3, "config": {"algo": "price_sensitive"}},
            {"type": "category_grid", "title": "特价分类", "priority": 4, "config": {"categories": "discounted"}},
            {"type": "live_stream", "title": "抄底直播间", "priority": 5, "config": {"type": "discount"}},
        ],
        "theme": "bright_red",
        "banner_strategy": "突出低价值权益",
        "discount_display": "显示省了多少钱",
    },
    UserSegment.CHURN_RISK: {
        "layout_type": "churn_retention",
        "modules": [
            {"type": "banner", "title": "我们想你了", "priority": 1, "config": {"style": "emotional"}},
            {"type": "flash_sale", "title": "回归专属优惠", "priority": 2, "config": {"discount": "exclusive", "time_limited": True}},
            {"type": "recommendation", "title": "最近大家都在看", "priority": 3, "config": {"algo": "trending"}},
            {"type": "category_grid", "title": "新品速递", "priority": 4, "config": {"categories": "new"}},
            {"type": "live_stream", "title": "精彩直播", "priority": 5, "config": {"auto_play": False}},
        ],
        "theme": "warm_pink",
        "banner_strategy": "情感唤回+大额优惠券",
        "discount_display": "突出回归专属优惠",
    },
    UserSegment.ACTIVE: {
        "layout_type": "active_discover",
        "modules": [
            {"type": "banner", "title": "今日必逛", "priority": 1, "config": {"style": "dynamic"}},
            {"type": "recommendation", "title": "根据您的喜好", "priority": 2, "config": {"algo": "personalized"}},
            {"type": "category_grid", "title": "常逛类目", "priority": 3, "config": {"categories": "preferred"}},
            {"type": "live_stream", "title": "关注的主播", "priority": 4, "config": {"following": True}},
            {"type": "flash_sale", "title": "限时特惠", "priority": 5, "config": {"discount": "moderate"}},
        ],
        "theme": "fresh_blue",
        "banner_strategy": "个性化动态Banner",
        "discount_display": "适中型折扣展示",
    },
}


class ContentPersonalizationAgent(BaseAgent):
    """Personalizes page layout and content based on user profile."""

    def __init__(self):
        settings = get_settings()
        super().__init__(name="content_personalization", timeout=6.0)
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.4,
            max_tokens=1024,
        )

    async def _execute(self, **kwargs: Any) -> ContentPersonalizationResult:
        user_profile: UserProfile | None = kwargs.get("user_profile")
        user_id: str = kwargs.get("user_id", "")
        scene: str = kwargs.get("scene", "homepage")

        segment = self._get_primary_segment(user_profile)
        base_template = MODULE_TEMPLATES.get(segment, MODULE_TEMPLATES[UserSegment.ACTIVE])

        messages = [
            SystemMessage(content="你是电商页面个性化设计专家。"),
            HumanMessage(content=LAYOUT_PROMPT.format(
                user_id=user_id,
                segments=[s.value for s in (user_profile.segments if user_profile else [])],
                categories=user_profile.preferred_categories if user_profile else [],
                price_range=user_profile.price_range if user_profile else (0, 10000),
                rfm=user_profile.rfm_score if user_profile else {},
                scene=scene,
            )),
        ]
        response = await self.llm.ainvoke(messages)

        llm_config = self._parse_layout(response.content)

        modules = llm_config.get("modules") or base_template["modules"]
        layout_config = {
            "layout_type": llm_config.get("layout_type", base_template["layout_type"]),
            "theme": llm_config.get("theme", base_template["theme"]),
            "banner_strategy": llm_config.get("banner_strategy", base_template["banner_strategy"]),
            "discount_display": llm_config.get("discount_display", base_template["discount_display"]),
            "scene": scene,
        }

        return ContentPersonalizationResult(
            success=True,
            layout_config=layout_config,
            modules=modules,
            personalization_factors=llm_config.get("personalization_factors", {}),
            data={"segment": segment.value if segment else "unknown", "raw_llm": response.content},
            confidence=0.85,
        )

    def _get_primary_segment(self, profile: UserProfile | None) -> UserSegment:
        if not profile or not profile.segments:
            return UserSegment.ACTIVE
        priority = [
            UserSegment.CHURN_RISK,
            UserSegment.HIGH_VALUE,
            UserSegment.NEW_USER,
            UserSegment.PRICE_SENSITIVE,
            UserSegment.ACTIVE,
        ]
        for seg in priority:
            if seg in profile.segments:
                return seg
        return UserSegment.ACTIVE

    def _parse_layout(self, raw: str) -> dict[str, Any]:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {}
