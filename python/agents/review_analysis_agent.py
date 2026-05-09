"""
评论分析Agent — 分析商品评论情感与洞察
- 评论情感分析：正面/负面/中性/混合
- 关键洞察提取：用户最关注的产品特性
- 评论聚合统计：评分分布、关键词提取
- 质量报告：为商家提供改进建议
"""

from __future__ import annotations

import json
import random
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import Review, ReviewAnalysisResult, SentimentLabel

from .base_agent import BaseAgent

REVIEW_ANALYSIS_PROMPT = """你是电商评论分析专家。分析以下商品评论数据。

商品ID: {product_id}
评论列表: {reviews}

请输出JSON格式的评论分析报告:
{{
  "overall_sentiment": "positive|negative|neutral|mixed",
  "sentiment_distribution": {{"positive": 0.0, "negative": 0.0, "neutral": 0.0, "mixed": 0.0}},
  "key_insights": ["洞察1: 用户最关心的方面...", "洞察2: 常见问题...", "洞察3: 改进建议..."],
  "top_positive_keywords": ["关键词1", "关键词2"],
  "top_negative_keywords": ["问题点1", "问题点2"]
}}
只输出JSON。"""

MOCK_REVIEWS_DATA: dict[str, list[dict[str, Any]]] = {
    "P001": [
        {"review_id": "R001", "product_id": "P001", "user_id": "U01", "rating": 5.0, "content": "性能强悍，拍照效果一流，系统流畅度完美"},
        {"review_id": "R002", "product_id": "P001", "user_id": "U02", "rating": 4.0, "content": "整体不错但价格偏高，续航有提升空间"},
        {"review_id": "R003", "product_id": "P001", "user_id": "U03", "rating": 3.0, "content": "发热问题明显，充电速度不如宣传"},
        {"review_id": "R004", "product_id": "P001", "user_id": "U04", "rating": 5.0, "content": "屏幕素质顶级，生态体验无敌"},
        {"review_id": "R005", "product_id": "P001", "user_id": "U05", "rating": 4.0, "content": "设计精致手感好，就是有点重"},
    ],
}


class ReviewAnalysisAgent(BaseAgent):
    """Analyzes product reviews for sentiment, insights, and quality reporting."""

    def __init__(self):
        settings = get_settings()
        super().__init__(name="review_analysis", timeout=8.0)
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.3,
            max_tokens=1024,
        )

    async def _execute(self, **kwargs: Any) -> ReviewAnalysisResult:
        product_id: str = kwargs.get("product_id", "")
        reviews_raw: list[dict] = kwargs.get("reviews", [])

        if not reviews_raw:
            reviews_raw = MOCK_REVIEWS_DATA.get(product_id, [])

        reviews = [Review(**r) for r in reviews_raw] if reviews_raw else []

        if not reviews:
            return ReviewAnalysisResult(
                success=True,
                product_id=product_id,
                overall_sentiment=SentimentLabel.NEUTRAL,
                sentiment_distribution={"positive": 0, "negative": 0, "neutral": 1.0, "mixed": 0},
                key_insights=["暂无足够评论数据进行分析"],
                confidence=0.5,
            )

        review_contents = "\n".join(f"- 评分:{r.rating} 内容:{r.content}" for r in reviews)
        messages = [
            SystemMessage(content="你是电商评论分析专家。"),
            HumanMessage(content=REVIEW_ANALYSIS_PROMPT.format(product_id=product_id, reviews=review_contents)),
        ]
        response = await self.llm.ainvoke(messages)

        analysis = self._parse_analysis(response.content, reviews)

        return ReviewAnalysisResult(
            success=True,
            product_id=product_id,
            overall_sentiment=analysis.get("overall_sentiment", SentimentLabel.NEUTRAL),
            sentiment_distribution=analysis.get("sentiment_distribution", {}),
            key_insights=analysis.get("key_insights", []),
            reviews=reviews,
            data={"raw_analysis": response.content},
            confidence=0.82,
        )

    def _parse_analysis(self, raw: str, reviews: list[Review]) -> dict[str, Any]:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            data = {}

        sentiment = data.get("overall_sentiment", "neutral")
        try:
            overall = SentimentLabel(sentiment)
        except ValueError:
            overall = SentimentLabel.NEUTRAL

        distribution = data.get("sentiment_distribution", {})
        if not distribution and reviews:
            pos = sum(1 for r in reviews if r.rating >= 4)
            neg = sum(1 for r in reviews if r.rating <= 2)
            neu = len(reviews) - pos - neg
            total = len(reviews)
            distribution = {
                "positive": round(pos / total, 2),
                "negative": round(neg / total, 2),
                "neutral": round(neu / total, 2),
                "mixed": 0.0,
            }

        return {
            "overall_sentiment": overall,
            "sentiment_distribution": distribution,
            "key_insights": data.get("key_insights", []),
        }
