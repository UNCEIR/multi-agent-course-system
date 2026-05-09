"""
欺诈检测Agent — 检测异常订单与账户风险
- 行为异常检测：下单频率、地址变更、设备指纹
- 支付风险：异常支付方式、金额异常、多地支付
- 账户风险：新注册高频下单、批量注册、刷单特征
- 风险评分：多维信号加权评分，输出风险等级
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import FraudDetectionResult, FraudRiskLevel

from .base_agent import BaseAgent

FRAUD_DETECTION_PROMPT = """你是电商风控反欺诈专家。分析以下交易信号，评估欺诈风险。

用户ID: {user_id}
订单信息: {order_info}
用户行为信号: {signals}

请输出JSON风险评估:
{{
  "risk_level": "low|medium|high|critical",
  "risk_score": 0-100的数字,
  "flags": ["风险信号1", "风险信号2"],
  "requires_review": true|false,
  "analysis": "风险评估说明"
}}
只输出JSON。"""

FRAUD_SIGNAL_WEIGHTS = {
    "new_account": 15,
    "high_velocity_orders": 25,
    "address_mismatch": 30,
    "unusual_ip": 20,
    "abnormal_amount": 20,
    "multiple_payments": 15,
    "device_fingerprint_change": 25,
    "gift_card_abuse": 35,
    "refund_abuse": 30,
    "account_sharing": 20,
    "shipping_forwarder": 15,
}


class FraudDetectionAgent(BaseAgent):
    """Detects fraudulent orders and accounts using multi-signal analysis."""

    def __init__(self):
        settings = get_settings()
        super().__init__(name="fraud_detection", timeout=6.0)
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.1,
            max_tokens=1024,
        )

    async def _execute(self, **kwargs: Any) -> FraudDetectionResult:
        user_id: str = kwargs.get("user_id", "")
        order_info: dict = kwargs.get("order_info", {})
        signals: dict = kwargs.get("signals", {})

        if not signals:
            signals = {
                "account_age_days": kwargs.get("account_age_days", 365),
                "orders_24h": kwargs.get("orders_24h", 1),
                "total_amount": kwargs.get("total_amount", 0),
                "payment_methods_used": kwargs.get("payment_methods_used", 1),
                "ip_changes_24h": kwargs.get("ip_changes_24h", 0),
                "address_changes_30d": kwargs.get("address_changes_30d", 0),
                "refund_rate": kwargs.get("refund_rate", 0.0),
            }

        rule_based_score = self._rule_based_scoring(signals)
        llm_assessment = await self._llm_assessment(user_id, order_info, signals)

        final_score = max(rule_based_score, llm_assessment.get("risk_score", 0))
        risk_level = self._score_to_level(final_score)
        flags = list(set(
            self._detect_flags(signals) + llm_assessment.get("flags", [])
        ))

        return FraudDetectionResult(
            success=True,
            risk_level=risk_level,
            risk_score=round(final_score, 1),
            flags=flags,
            requires_review=final_score >= 50,
            signals=signals,
            data={"rule_score": rule_based_score, "llm_score": llm_assessment.get("risk_score", 0)},
            confidence=0.90,
        )

    def _rule_based_scoring(self, signals: dict) -> float:
        score = 0.0

        if signals.get("account_age_days", 365) < 7:
            score += FRAUD_SIGNAL_WEIGHTS["new_account"]
        if signals.get("orders_24h", 0) > 5:
            score += FRAUD_SIGNAL_WEIGHTS["high_velocity_orders"]
        if signals.get("ip_changes_24h", 0) > 3:
            score += FRAUD_SIGNAL_WEIGHTS["unusual_ip"]
        if signals.get("address_changes_30d", 0) > 3:
            score += FRAUD_SIGNAL_WEIGHTS["address_mismatch"]
        if signals.get("total_amount", 0) > 50000:
            score += FRAUD_SIGNAL_WEIGHTS["abnormal_amount"]
        if signals.get("payment_methods_used", 1) > 3:
            score += FRAUD_SIGNAL_WEIGHTS["multiple_payments"]
        if signals.get("refund_rate", 0) > 0.5:
            score += FRAUD_SIGNAL_WEIGHTS["refund_abuse"]

        return min(score, 100.0)

    async def _llm_assessment(self, user_id: str, order_info: dict, signals: dict) -> dict[str, Any]:
        messages = [
            SystemMessage(content="你是电商风控反欺诈专家。"),
            HumanMessage(content=FRAUD_DETECTION_PROMPT.format(
                user_id=user_id,
                order_info=json.dumps(order_info, ensure_ascii=False),
                signals=json.dumps(signals, ensure_ascii=False),
            )),
        ]
        response = await self.llm.ainvoke(messages)
        try:
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(raw)
        except (json.JSONDecodeError, IndexError):
            return {"risk_level": "low", "risk_score": 0, "flags": [], "requires_review": False}

    def _detect_flags(self, signals: dict) -> list[str]:
        flags = []
        if signals.get("account_age_days", 365) < 7:
            flags.append("新账户(注册<7天)")
        if signals.get("orders_24h", 0) > 5:
            flags.append(f"高频下单({signals['orders_24h']}单/24h)")
        if signals.get("ip_changes_24h", 0) > 3:
            flags.append(f"IP频繁变更({signals['ip_changes_24h']}次/24h)")
        if signals.get("address_changes_30d", 0) > 3:
            flags.append(f"收货地址频繁变更({signals['address_changes_30d']}次/30d)")
        if signals.get("total_amount", 0) > 50000:
            flags.append(f"异常大额交易(¥{signals['total_amount']})")
        if signals.get("refund_rate", 0) > 0.5:
            flags.append(f"高退款率({signals['refund_rate']:.0%})")
        return flags

    def _score_to_level(self, score: float) -> FraudRiskLevel:
        if score >= 80:
            return FraudRiskLevel.CRITICAL
        if score >= 60:
            return FraudRiskLevel.HIGH
        if score >= 30:
            return FraudRiskLevel.MEDIUM
        return FraudRiskLevel.LOW
