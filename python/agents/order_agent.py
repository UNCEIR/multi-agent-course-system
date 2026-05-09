from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import get_settings
from models.schemas import Product, UserProfile

from .base_agent import BaseAgent

SYSTEM_PROMPT = """你是一个电商订单管理专家。根据用户请求，执行以下订单操作：

1. **订单查询**：根据订单ID查询订单状态
2. **订单历史**：获取用户近期订单列表
3. **取消订单**：检查取消条件（是否已发货、是否在可取消窗口内）
4. **物流追踪**：获取物流最新状态
5. **发票管理**：申请/查询电子发票
6. **售后处理**：退换货申请状态

输出JSON格式：
{
  "action": "query_order/order_history/cancel_order/track_logistics/invoice/manage_after_sale",
  "orders": [{"order_id": "xxx", "status": "pending/confirmed/shipped/delivered/cancelled/refunding/refunded", "items": [...], "total_amount": 0, "created_at": "...", "logistics": {...}}],
  "can_cancel": true/false,
  "cancel_reason": "原因（如不可取消）",
  "suggestions": ["建议1", "建议2"],
  "confidence": 0.0-1.0
}
只输出JSON，不要其他内容。"""

ORDER_STATUS_TRANSITIONS = {
    "pending": ["confirmed", "cancelled"],
    "confirmed": ["shipped", "cancelled"],
    "shipped": ["delivered"],
    "delivered": ["refunding"],
    "refunding": ["refunded"],
    "cancelled": [],
    "refunded": [],
}

CANCELABLE_STATUSES = {"pending", "confirmed"}
REFUNDABLE_STATUSES = {"delivered", "refunding"}

MOCK_ORDERS = [
    {
        "order_id": "ORD-20260001",
        "status": "delivered",
        "items": [
            {"product_id": "P001", "name": "iPhone 16 Pro", "price": 7999, "quantity": 1},
        ],
        "total_amount": 7999,
        "created_at": (datetime.now() - timedelta(days=14)).isoformat(),
        "logistics": {"carrier": "顺丰速运", "tracking": "SF1234567890", "status": "已签收", "eta": None},
        "payment_method": "微信支付",
        "shipping_address": "北京市朝阳区xxx路xxx号",
    },
    {
        "order_id": "ORD-20260002",
        "status": "shipped",
        "items": [
            {"product_id": "P003", "name": "AirPods Pro 3", "price": 1899, "quantity": 2},
        ],
        "total_amount": 3798,
        "created_at": (datetime.now() - timedelta(days=5)).isoformat(),
        "logistics": {"carrier": "中通快递", "tracking": "ZTO9876543210", "status": "运输中", "eta": "预计2026-05-11送达"},
        "payment_method": "支付宝",
        "shipping_address": "上海市浦东新区xxx路xxx号",
    },
    {
        "order_id": "ORD-20260003",
        "status": "pending",
        "items": [
            {"product_id": "P012", "name": "绿联氮化镓65W", "price": 129, "quantity": 3},
        ],
        "total_amount": 387,
        "created_at": (datetime.now() - timedelta(hours=2)).isoformat(),
        "logistics": {},
        "payment_method": "微信支付",
        "shipping_address": "深圳市南山区xxx科技园",
    },
    {
        "order_id": "ORD-20260004",
        "status": "confirmed",
        "items": [
            {"product_id": "P008", "name": "机械革命极光X", "price": 6999, "quantity": 1},
            {"product_id": "P010", "name": "罗技MX Master 3S", "price": 749, "quantity": 1},
        ],
        "total_amount": 7748,
        "created_at": (datetime.now() - timedelta(days=1)).isoformat(),
        "logistics": {},
        "payment_method": "花呗分期",
        "shipping_address": "杭州市西湖区xxx路xxx号",
    },
    {
        "order_id": "ORD-20260005",
        "status": "refunding",
        "items": [
            {"product_id": "P007", "name": "Anker 140W充电器", "price": 399, "quantity": 1},
        ],
        "total_amount": 399,
        "created_at": (datetime.now() - timedelta(days=20)).isoformat(),
        "logistics": {},
        "payment_method": "微信支付",
        "shipping_address": "广州市天河区xxx路xxx号",
    },
]


class OrderAgent(BaseAgent):
    def __init__(self):
        settings = get_settings()
        super().__init__(
            name="order",
            timeout=settings.agent_timeout_inventory,
        )
        self.llm = ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=0.2,
            max_tokens=1024,
        )

    async def _execute(self, **kwargs: Any) -> dict:
        user_profile: UserProfile | None = kwargs.get("user_profile")
        user_id: str = kwargs.get("user_id", "")
        action: str = kwargs.get("action", "query_order")
        order_id: str = kwargs.get("order_id", "")
        products: list[Product] = kwargs.get("products", [])
        context: dict = kwargs.get("context", {})

        result = {}

        if action == "query_order" and order_id:
            result = self._query_order(order_id)
        elif action == "order_history":
            result = self._get_order_history(user_id)
        elif action == "cancel_order" and order_id:
            result = self._cancel_order(order_id)
        elif action == "track_logistics" and order_id:
            result = self._track_logistics(order_id)
        elif action == "create_order":
            result = self._create_order(user_id, products, context)
        else:
            result = await self._understand_and_act(user_id, action, context)

        return {
            "success": True,
            "agent_name": "order",
            "data": result,
            "confidence": 0.9,
        }

    def _query_order(self, order_id: str) -> dict:
        for order in MOCK_ORDERS:
            if order["order_id"] == order_id:
                return {
                    "found": True,
                    "order": order,
                    "can_cancel": order["status"] in CANCELABLE_STATUSES,
                    "can_refund": order["status"] in REFUNDABLE_STATUSES,
                    "suggestions": self._get_suggestions(order["status"]),
                }
        return {"found": False, "message": f"订单{order_id}不存在"}

    def _get_order_history(self, user_id: str) -> dict:
        return {
            "orders": MOCK_ORDERS,
            "total_orders": len(MOCK_ORDERS),
            "total_spent": sum(o["total_amount"] for o in MOCK_ORDERS),
            "active_orders": [o for o in MOCK_ORDERS if o["status"] in ("pending", "confirmed", "shipped")],
            "completed_orders": [o for o in MOCK_ORDERS if o["status"] == "delivered"],
        }

    def _cancel_order(self, order_id: str) -> dict:
        order_info = self._query_order(order_id)
        if not order_info["found"]:
            return order_info
        if not order_info["can_cancel"]:
            return {
                "success": False,
                "order_id": order_id,
                "message": "订单已发货或已完成，无法取消。建议申请退换货。",
                "alternative_action": "refund",
            }
        order_info["order"]["status"] = "cancelled"
        return {
            "success": True,
            "order_id": order_id,
            "message": "订单已成功取消，款项将在3-5个工作日内退回。",
            "refund_amount": order_info["order"]["total_amount"],
        }

    def _track_logistics(self, order_id: str) -> dict:
        for order in MOCK_ORDERS:
            if order["order_id"] == order_id:
                if order["logistics"]:
                    return {
                        "order_id": order_id,
                        "status": order["status"],
                        "logistics": order["logistics"],
                    }
                return {"order_id": order_id, "message": "订单尚未发货，暂无物流信息。"}
        return {"found": False, "message": f"订单{order_id}不存在"}

    def _create_order(
        self, user_id: str, products: list[Product], context: dict
    ) -> dict:
        if not products:
            return {"success": False, "message": "购物车为空"}

        order_id = f"ORD-{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:4].upper()}"
        total = sum(p.price for p in products)

        new_order = {
            "order_id": order_id,
            "status": "pending",
            "items": [
                {"product_id": p.product_id, "name": p.name, "price": p.price, "quantity": 1}
                for p in products
            ],
            "total_amount": total,
            "created_at": datetime.now().isoformat(),
            "logistics": {},
            "payment_method": context.get("payment_method", "微信支付"),
            "shipping_address": context.get("shipping_address", ""),
        }

        return {
            "success": True,
            "order": new_order,
            "message": f"订单创建成功！订单号：{order_id}，金额：¥{total}",
        }

    async def _understand_and_act(
        self, user_id: str, query: str, context: dict
    ) -> dict:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"用户请求: {query}\n上下文: {json.dumps(context, ensure_ascii=False)}"),
        ]
        response = await self.llm.ainvoke(messages)
        try:
            cleaned = response.content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            analysis = json.loads(cleaned)
            return {
                "action": analysis.get("action", "query_order"),
                "orders": analysis.get("orders", []),
                "can_cancel": analysis.get("can_cancel", False),
                "suggestions": analysis.get("suggestions", []),
                "confidence": analysis.get("confidence", 0.7),
            }
        except (json.JSONDecodeError, IndexError):
            return {"action": "query_order", "suggestions": ["请联系人工客服处理"]}

    def _get_suggestions(self, status: str) -> list[str]:
        suggestions = {
            "pending": ["及时完成支付以确认订单", "如需修改收货信息请尽快操作"],
            "confirmed": ["商家正在备货，预计24小时内发货", "可通过物流追踪查看配送进度"],
            "shipped": ["关注物流更新，注意签收", "收货时请检查包裹完整性"],
            "delivered": ["对商品满意可以分享评价", "如有质量问题可在7天内申请售后"],
            "refunding": ["退款处理中，请耐心等待", "退款到账时间视支付方式而定"],
            "refunded": ["退款已完成", "欢迎再次选购"],
            "cancelled": ["订单已取消", "欢迎再次选购"],
        }
        return suggestions.get(status, [])
