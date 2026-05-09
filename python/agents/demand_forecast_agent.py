"""
需求预测Agent — 基于多维度数据预测商品需求
- 销量趋势分析：历史销量序列分析
- 季节性因素：节假日、季节、大促影响
- 价格弹性：价格变化对销量的影响
- 补货建议：安全库存、补货点、补货量
"""

from __future__ import annotations

import json
import random
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import DemandForecastResult, DemandLevel, Product

from .base_agent import BaseAgent

FORECAST_PROMPT = """你是电商需求预测专家。根据历史数据和市场因素预测商品需求。

商品信息: {product_info}
历史销量(近30天每日): {sales_history}
当前库存: {current_stock}
市场因素: {market_factors}

请输出JSON需求预测:
{{
  "forecast_7d": 未来7天预测销量(数字),
  "forecast_30d": 未来30天预测销量(数字),
  "demand_level": "low|normal|high|surge",
  "trend": "increasing|stable|decreasing",
  "confidence_interval": {{"lower": 下限, "upper": 上限}},
  "restock_recommendation": "补货建议文字",
  "factors_analysis": {{
    "seasonal_impact": "季节性影响说明",
    "price_elasticity": "价格弹性说明",
    "market_trend": "市场趋势说明"
  }}
}}
只输出JSON。"""


class DemandForecastAgent(BaseAgent):
    """Predicts product demand using historical data and market factors."""

    def __init__(self):
        settings = get_settings()
        super().__init__(name="demand_forecast", timeout=8.0)
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.3,
            max_tokens=1024,
        )

    async def _execute(self, **kwargs: Any) -> DemandForecastResult:
        product: Product | None = kwargs.get("product")
        product_id: str = kwargs.get("product_id", product.product_id if product else "unknown")
        current_stock: int = kwargs.get("current_stock", product.stock if product else 0)
        sales_history: list[int] = kwargs.get("sales_history", [])
        market_factors: dict = kwargs.get("market_factors", {})

        if not sales_history:
            sales_history = self._generate_mock_sales_history()

        if not market_factors:
            market_factors = {
                "season": "spring",
                "upcoming_promotion": "618大促",
                "competitor_activity": "normal",
                "trend_direction": "stable",
            }

        product_info = f"商品:{product.name} 类目:{product.category}" if product else f"商品ID:{product_id}"

        if product:
            product_info = f"商品:{product.name} 类目:{product.category} 价格:¥{product.price}"

        messages = [
            SystemMessage(content="你是电商需求预测专家。"),
            HumanMessage(content=FORECAST_PROMPT.format(
                product_info=product_info,
                sales_history=json.dumps(sales_history),
                current_stock=current_stock,
                market_factors=json.dumps(market_factors, ensure_ascii=False),
            )),
        ]
        response = await self.llm.ainvoke(messages)

        forecast_data = self._parse_forecast(response.content, sales_history, current_stock)

        demand_level_str = forecast_data.get("demand_level", "normal")
        try:
            demand_level = DemandLevel(demand_level_str)
        except ValueError:
            demand_level = DemandLevel.NORMAL

        return DemandForecastResult(
            success=True,
            product_id=product_id,
            forecast_7d=forecast_data.get("forecast_7d", 0),
            forecast_30d=forecast_data.get("forecast_30d", 0),
            demand_level=demand_level,
            confidence_interval=forecast_data.get("confidence_interval", {}),
            restock_recommendation=forecast_data.get("restock_recommendation", ""),
            data={
                "trend": forecast_data.get("trend", "stable"),
                "factors_analysis": forecast_data.get("factors_analysis", {}),
                "current_stock": current_stock,
            },
            confidence=0.78,
        )

    def _generate_mock_sales_history(self) -> list[int]:
        base = random.randint(10, 50)
        return [max(1, base + random.randint(-10, 15)) for _ in range(30)]

    def _parse_forecast(self, raw: str, sales_history: list[int], stock: int) -> dict[str, Any]:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            avg_daily = sum(sales_history) / max(len(sales_history), 1)
            return {
                "forecast_7d": round(avg_daily * 7),
                "forecast_30d": round(avg_daily * 30),
                "demand_level": "normal",
                "trend": "stable",
                "confidence_interval": {"lower": round(avg_daily * 0.7 * 7), "upper": round(avg_daily * 1.3 * 7)},
                "restock_recommendation": f"建议维持安全库存{stock}件" if stock > 0 else "暂无库存数据",
                "factors_analysis": {},
            }
