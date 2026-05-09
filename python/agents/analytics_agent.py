"""
数据分析Agent — 商业智能洞察与决策支持
- KPI汇总：GMV/转化率/客单价/复购率
- 趋势分析：周/月/季度对比
- 异常检测：指标突增/突降告警
- 决策建议：基于数据的可执行建议
"""

from __future__ import annotations

import json
import random
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import AnalyticsResult

from .base_agent import BaseAgent

ANALYTICS_PROMPT = """你是电商商业分析专家。根据业务数据生成商业洞察报告。

业务数据:
{business_data}

分析维度: {dimensions}
时间范围: {time_range}

请输出JSON分析报告:
{{
  "insights": [
    {{"type": "trend|anomaly|opportunity|risk", "title": "洞察标题", "detail": "详细说明", "impact": "high|medium|low", "metric": "相关指标", "change": "变化百分比"}}
  ],
  "kpi_summary": {{
    "gmv": 总交易额,
    "conversion_rate": 转化率(小数),
    "average_order_value": 客单价,
    "repurchase_rate": 复购率(小数),
    "active_users": 活跃用户数,
    "new_users": 新增用户数
  }},
  "business_health_score": 0-100,
  "recommendations": ["建议1", "建议2", "建议3"],
  "charts_data": {{
    "sales_trend": [每日或每月销售额列表],
    "category_distribution": {{"类目1": 占比, "类目2": 占比}},
    "user_segment_distribution": {{"新客": 占比, "老客": 占比}}
  }}
}}
只输出JSON。"""


class AnalyticsAgent(BaseAgent):
    """Generates business intelligence insights and recommendations."""

    def __init__(self):
        settings = get_settings()
        super().__init__(name="analytics", timeout=10.0)
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.4,
            max_tokens=2048,
        )

    async def _execute(self, **kwargs: Any) -> AnalyticsResult:
        business_data: dict = kwargs.get("business_data", {})
        dimensions: list[str] = kwargs.get("dimensions", ["sales", "users", "products", "categories"])
        time_range: str = kwargs.get("time_range", "最近30天")

        if not business_data:
            business_data = self._generate_mock_business_data()

        messages = [
            SystemMessage(content="你是电商商业分析专家。"),
            HumanMessage(content=ANALYTICS_PROMPT.format(
                business_data=json.dumps(business_data, ensure_ascii=False),
                dimensions=json.dumps(dimensions, ensure_ascii=False),
                time_range=time_range,
            )),
        ]
        response = await self.llm.ainvoke(messages)

        analysis = self._parse_analysis(response.content, business_data)

        return AnalyticsResult(
            success=True,
            insights=analysis.get("insights", []),
            kpi_summary=analysis.get("kpi_summary", {}),
            recommendations=analysis.get("recommendations", []),
            charts_data=analysis.get("charts_data", {}),
            data={
                "business_health_score": analysis.get("business_health_score", 0),
                "time_range": time_range,
                "dimensions": dimensions,
            },
            confidence=0.82,
        )

    def _generate_mock_business_data(self) -> dict[str, Any]:
        return {
            "total_gmv_30d": random.randint(500000, 2000000),
            "total_orders_30d": random.randint(2000, 8000),
            "active_users_30d": random.randint(5000, 20000),
            "new_users_30d": random.randint(500, 3000),
            "conversion_rate": round(random.uniform(0.02, 0.08), 3),
            "average_order_value": round(random.uniform(150, 500), 1),
            "repurchase_rate": round(random.uniform(0.15, 0.45), 3),
            "refund_rate": round(random.uniform(0.01, 0.08), 3),
            "sales_trend": [random.randint(10000, 50000) for _ in range(30)],
            "top_categories": {
                "手机数码": 0.35,
                "家用电器": 0.20,
                "服饰鞋包": 0.18,
                "食品生鲜": 0.12,
                "美妆个护": 0.10,
                "其他": 0.05,
            },
            "user_segments": {
                "新用户": 0.25,
                "活跃用户": 0.35,
                "高价值用户": 0.15,
                "价格敏感用户": 0.15,
                "流失风险用户": 0.10,
            },
        }

    def _parse_analysis(self, raw: str, fallback_data: dict) -> dict[str, Any]:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {
                "insights": [],
                "kpi_summary": {
                    "gmv": fallback_data.get("total_gmv_30d", 0),
                    "conversion_rate": fallback_data.get("conversion_rate", 0),
                    "average_order_value": fallback_data.get("average_order_value", 0),
                    "repurchase_rate": fallback_data.get("repurchase_rate", 0),
                    "active_users": fallback_data.get("active_users_30d", 0),
                    "new_users": fallback_data.get("new_users_30d", 0),
                },
                "business_health_score": 70,
                "recommendations": [],
                "charts_data": {},
            }
