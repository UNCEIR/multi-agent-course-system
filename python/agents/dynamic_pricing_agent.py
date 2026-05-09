"""
动态定价Agent — 基于多维因素的智能定价
- 需求弹性分析：销量与价格关系
- 竞争定价：竞品价格监控与对标
- 库存驱动定价：库存深度 -> 折扣力度
- 用户价格敏感度：用户历史行为 -> 个性化定价
- 时效性定价：季节性、促销活动、限时调整
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import DynamicPricingResult, Product

from .base_agent import BaseAgent

PRICING_PROMPT = """你是电商动态定价专家。根据以下信息推荐最优价格。

商品信息: {product_info}
库存深度: {stock}
需求趋势: {demand_trend}
用户价格敏感度: {price_sensitivity}
竞品价格: {competitor_prices}

请输出JSON定价建议:
{{
  "recommended_price": 调整后价格(数字),
  "price_adjustment_strategy": "discount|premium|maintain|promotion",
  "factors": {{
    "stock_pressure": 库存对价格的影响说明,
    "demand_signal": 需求对价格的影响说明,
    "competition_impact": 竞争对价格的影响说明,
    "user_sensitivity_impact": 用户敏感度对价格的影响说明
  }},
  "reason": "定价理由简要说明"
}}
只输出JSON。"""


class DynamicPricingAgent(BaseAgent):
    """Intelligent pricing agent considering demand, competition, stock, and user behavior."""

    def __init__(self):
        settings = get_settings()
        super().__init__(name="dynamic_pricing", timeout=8.0)
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.3,
            max_tokens=1024,
        )

    async def _execute(self, **kwargs: Any) -> DynamicPricingResult:
        product: Product | None = kwargs.get("product")
        stock: int = kwargs.get("stock", 0)
        demand_trend: str = kwargs.get("demand_trend", "normal")
        price_sensitivity: str = kwargs.get("price_sensitivity", "moderate")
        competitor_prices: str = kwargs.get("competitor_prices", "无竞品数据")

        if product is None:
            product_id = kwargs.get("product_id", "unknown")
            original_price = kwargs.get("original_price", 0.0)
            product_info = f"商品ID:{product_id} 价格:{original_price}"
        else:
            product_id = product.product_id
            original_price = product.price
            product_info = f"商品:{product.name} 类目:{product.category} 原价:¥{product.price} 品牌:{product.brand} 标签:{','.join(product.tags)}"

        messages = [
            SystemMessage(content="你是电商动态定价专家。"),
            HumanMessage(content=PRICING_PROMPT.format(
                product_info=product_info,
                stock=stock,
                demand_trend=demand_trend,
                price_sensitivity=price_sensitivity,
                competitor_prices=competitor_prices,
            )),
        ]
        response = await self.llm.ainvoke(messages)

        pricing_data = self._parse_pricing(response.content, original_price)

        return DynamicPricingResult(
            success=True,
            product_id=product_id,
            original_price=original_price,
            recommended_price=pricing_data.get("recommended_price", original_price),
            price_adjustment_strategy=pricing_data.get("price_adjustment_strategy", "maintain"),
            factors=pricing_data.get("factors", {}),
            data={"raw_response": response.content},
            confidence=0.80,
        )

    def _parse_pricing(self, raw: str, fallback_price: float) -> dict[str, Any]:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {"recommended_price": fallback_price, "price_adjustment_strategy": "maintain", "factors": {}}
