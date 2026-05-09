from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import IntentRecognitionResult, IntentType

from .base_agent import BaseAgent

SYSTEM_PROMPT = """你是一个电商用户意图识别专家。
分析用户的行为上下文和输入查询,识别其真实意图。

意图类型(browse/search/purchase/compare/support/return_request):
- browse: 用户正在随便浏览,无明确购买目标
- search: 用户有明确搜索目标,正在寻找特定商品
- purchase: 用户有强烈购买意向,准备下单
- compare: 用户正在对比多个商品
- support: 用户需要客服帮助
- return_request: 用户想要退换货

输出JSON:
{
  "intent": "意图类型",
  "confidence": 0.0-1.0,
  "extracted_entities": {
    "target_category": "目标类目",
    "target_brand": "目标品牌",
    "budget_range": [最低, 最高],
    "specific_requirements": ["要求1", "要求2"],
    "urgency_level": "low"|"medium"|"high"
  },
  "reasoning": "简短分析依据"
}

只输出JSON,不要其他内容。"""


class IntentRecognitionAgent(BaseAgent):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            name="intent_recognition",
            timeout=settings.agent_timeout_intent_recognition,
        )
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.2,
            max_tokens=512,
        )

    async def _execute(self, **kwargs: Any) -> IntentRecognitionResult:
        user_id: str = kwargs["user_id"]
        context: dict = kwargs.get("context", {})
        query: str = kwargs.get("query", "")
        scene: str = kwargs.get("scene", "homepage")
        profile_segments: list = kwargs.get("profile_segments", [])

        intent_data = await self._recognize(user_id, context, query, scene, profile_segments)

        intent = IntentType.BROWSE
        try:
            intent = IntentType(intent_data.get("intent", "browse"))
        except ValueError:
            pass

        return IntentRecognitionResult(
            success=True,
            intent=intent,
            confidence_score=float(intent_data.get("confidence", 0.5)),
            extracted_entities=intent_data.get("extracted_entities", {}),
            data={"reasoning": intent_data.get("reasoning", ""), "query": query},
            confidence=float(intent_data.get("confidence", 0.5)),
        )

    async def _recognize(
        self, user_id: str, context: dict, query: str, scene: str, profile_segments: list
    ) -> dict:
        if not query and scene in ("homepage", "category"):
            return {"intent": "browse", "confidence": 0.9, "extracted_entities": {}, "reasoning": "首页浏览场景"}

        input_data = {
            "user_id": user_id,
            "scene": scene,
            "query": query,
            "user_segments": profile_segments,
            "context": context,
        }

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(input_data, ensure_ascii=False)),
        ]
        response = await self.llm.ainvoke(messages)
        return self._parse_json(response.content)

    def _parse_json(self, raw: str) -> dict:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {"intent": "browse", "confidence": 0.5, "extracted_entities": {}}
