"""
客服Agent — 智能售后支持与FAQ
- 意图识别：退货/换货/咨询/投诉分类
- 知识库检索：FAQ匹配与答案生成
- 工单创建：复杂问题自动升级
- 情感安抚：针对投诉用户的情绪安抚话术
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import CustomerServiceResult

from .base_agent import BaseAgent

INTENT_CLASSIFY_PROMPT = """你是电商客服意图识别专家。识别用户问题的意图和紧急程度。

用户消息: {user_message}
用户ID: {user_id}
订单历史: {order_history}

请输出JSON:
{{
  "intent": "return|exchange|complaint|inquiry|feedback|technical",
  "urgency": "low|normal|high|critical",
  "sentiment": "calm|frustrated|angry|satisfied",
  "key_entities": {{"product": "...", "order_id": "..."}},
  "requires_escalation": true|false,
  "action_items": [{{"action": "...", "reason": "..."}}]
}}
只输出JSON。"""

FAQ_KNOWLEDGE = {
    "return": "您可以在订单详情页申请退货退款。符合7天无理由退货的商品，我们将全额退款并承担运费。退货流程：我的订单 -> 选择商品 -> 申请退货 -> 填写原因 -> 等待审核。",
    "exchange": "换货流程：我的订单 -> 选择商品 -> 申请换货 -> 选择换货商品 -> 等待审核。换货运费由商家承担。审核通常1-2个工作日内完成。",
    "complaint": "非常抱歉给您带来不便。我已记录您的投诉（投诉编号将稍后生成），会在24小时内由专人跟进处理。如有紧急需要，可拨打客服热线 400-888-8888。",
    "inquiry": "很高兴为您解答。您的问题我们已经收到，正在为您查询相关信息。同时您也可以查看帮助中心获取更多产品使用指南。",
    "feedback": "感谢您的宝贵反馈！您的建议我们已经记录，将会转交相关部门评估改进。作为答谢，赠送您一张优惠券，请注意查收。",
    "technical": "技术问题已受理。请您提供更多信息（设备型号、系统版本、问题截图），我们的技术团队将在2小时内为您排查处理。",
}

COMFORT_PHRASES = {
    "frustrated": "我们完全理解您的感受，这确实不应该发生。",
    "angry": "非常抱歉给您带来如此糟糕的体验，我代表团队向您致歉。",
    "calm": "感谢您的耐心反馈，我们会认真处理。",
    "satisfied": "很高兴能帮到您！如有其他问题随时联系我们。",
}


class CustomerServiceAgent(BaseAgent):
    """Intelligent customer service with intent recognition and FAQ matching."""

    def __init__(self):
        settings = get_settings()
        super().__init__(name="customer_service", timeout=8.0)
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.5,
            max_tokens=1024,
        )

    async def _execute(self, **kwargs: Any) -> CustomerServiceResult:
        user_message: str = kwargs.get("user_message", "")
        user_id: str = kwargs.get("user_id", "")
        order_history: str = kwargs.get("order_history", "无历史订单")

        if not user_message:
            return CustomerServiceResult(
                success=True,
                response="请问有什么可以帮您的？",
                intent="unknown",
                confidence=1.0,
            )

        intent_data = await self._classify_intent(user_message, user_id, order_history)
        intent = intent_data.get("intent", "inquiry")
        sentiment = intent_data.get("sentiment", "calm")
        escalation = intent_data.get("requires_escalation", False)

        comfort = COMFORT_PHRASES.get(sentiment, "")
        faq_answer = FAQ_KNOWLEDGE.get(intent, FAQ_KNOWLEDGE["inquiry"])

        response = f"{comfort} {faq_answer}"

        if escalation:
            response += " 该问题已升级至高级客服团队，稍后会有专人联系您。"

        return CustomerServiceResult(
            success=True,
            response=response,
            intent=intent,
            action_items=intent_data.get("action_items", []),
            escalation_needed=escalation,
            data={
                "intent_data": intent_data,
                "sentiment": sentiment,
            },
            confidence=0.88,
        )

    async def _classify_intent(self, message: str, user_id: str, order_history: str) -> dict[str, Any]:
        messages = [
            SystemMessage(content="你是电商客服意图识别专家。"),
            HumanMessage(content=INTENT_CLASSIFY_PROMPT.format(
                user_message=message, user_id=user_id, order_history=order_history
            )),
        ]
        response = await self.llm.ainvoke(messages)
        try:
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            return {"intent": "inquiry", "urgency": "normal", "sentiment": "calm", "requires_escalation": False, "action_items": []}
