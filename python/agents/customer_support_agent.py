from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import (
    CustomerServiceResult,
    SentimentPolarity,
    ServiceAction,
    UserProfile,
)

from .base_agent import BaseAgent

SYSTEM_PROMPT = """你是一个电商智能客服专家。分析用户的客服请求，完成以下任务：

1. **意图分类**：判断用户请求类型（咨询/投诉/退货/退款/物流查询/产品问题）
2. **情感分析**：分析用户情绪（positive/neutral/negative/mixed）
3. **问题严重度**：评估问题紧急程度（low/medium/high/critical）
4. **行动决策**：决定处理方式（auto_reply/escalate_human/refund_initiate/coupon_issue/none）

行动决策规则：
- 简单咨询 → auto_reply
- 投诉/负面情绪 → escalate_human
- 退货/退款请求 → refund_initiate
- 物流延迟/质量问题 → escalate_human + coupon_issue
- 无法判断 → escalate_human

输出JSON格式：
{
  "intent": "咨询/投诉/退货/退款/物流查询/产品问题",
  "sentiment": "positive/neutral/negative/mixed",
  "severity": "low/medium/high/critical",
  "action": "auto_reply/escalate_human/refund_initiate/coupon_issue/none",
  "auto_reply": "自动回复内容（如果action=auto_reply）",
  "escalation_reason": "升级原因（如果action=escalate_human）",
  "confidence": 0.0-1.0
}
只输出JSON，不要其他内容。"""

AUTO_REPLY_TEMPLATES = {
    "咨询": "您好！感谢您的咨询。关于{product}的问题，我们的客服团队会尽快为您提供详细解答。平均响应时间约5分钟。",
    "物流查询": "您好！您的订单{order_id}物流状态已更新，预计{eta}送达。您可以通过物流号{tracking}实时追踪配送进度。",
    "产品问题": "您好！对于{product}的使用问题，建议您先查看以下快速排查步骤：1)重启设备 2)检查连接 3)更新固件。如果问题仍然存在，我们的技术支持团队将在24小时内联系您。",
    "退货": "您好！我们已收到您的退货申请（订单号：{order_id}）。请将商品保持原包装退回，退货地址将通过短信发送给您。处理时间约为3-5个工作日。",
    "退款": "您好！您的退款申请（订单号：{order_id}）正在处理中。退款将在3-7个工作日内原路退回至您的支付账户。请耐心等待。",
    "投诉": "您好！非常抱歉给您带来了不愉快的体验。我们已将您的问题升级至高级客服专员，将在2小时内与您联系处理。同时为您发放了一张补偿优惠券，可在下次购物时使用。",
}


class CustomerSupportAgent(BaseAgent):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            name="customer_support",
            timeout=settings.agent_timeout_customer_service,
        )
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.3,
            max_tokens=1024,
        )

    async def _execute(self, **kwargs: Any) -> CustomerServiceResult:
        user_profile: UserProfile | None = kwargs.get("user_profile")
        query: str = kwargs.get("query", "")
        context: dict = kwargs.get("context", {})

        if not query:
            return CustomerServiceResult(
                success=True,
                action=ServiceAction.NONE,
                confidence=1.0,
                data={"message": "no query provided"},
            )

        analysis = await self._analyze_query(query, user_profile, context)
        auto_reply = self._generate_reply(analysis, context)

        action = ServiceAction(analysis.get("action", "none"))
        sentiment = SentimentPolarity(analysis.get("sentiment", "neutral"))

        return CustomerServiceResult(
            success=True,
            action=action,
            auto_reply=auto_reply,
            escalation_reason=analysis.get("escalation_reason"),
            confidence=analysis.get("confidence", 0.7),
            data={
                "intent": analysis.get("intent", ""),
                "sentiment": sentiment.value,
                "severity": analysis.get("severity", "low"),
                "raw_analysis": analysis,
            },
        )

    async def _analyze_query(
        self, query: str, profile: UserProfile | None, context: dict
    ) -> dict:
        user_info = ""
        if profile:
            segments = [s.value for s in profile.segments]
            user_info = f"用户画像: 等级={segments}, 偏好类目={profile.preferred_categories}, 价格区间={profile.price_range}"

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"{user_info}\n客服请求: {query}\n上下文: {json.dumps(context, ensure_ascii=False)}"),
        ]
        response = await self.llm.ainvoke(messages)
        return self._parse_json(response.content)

    def _generate_reply(self, analysis: dict, context: dict) -> str:
        action = analysis.get("action", "")
        if action != "auto_reply":
            return ""

        intent = analysis.get("intent", "咨询")
        template = AUTO_REPLY_TEMPLATES.get(intent, AUTO_REPLY_TEMPLATES["咨询"])

        product = context.get("product_name", "相关商品")
        order_id = context.get("order_id", "N/A")
        eta = context.get("eta", "2-3个工作日")
        tracking = context.get("tracking", "N/A")

        return template.format(
            product=product,
            order_id=order_id,
            eta=eta,
            tracking=tracking,
        )

    def _parse_json(self, raw: str) -> dict:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {"action": "escalate_human", "confidence": 0.3}
