# -*- coding: utf-8 -*-
"""统一 HTTP 响应信封（市场规范：{code, success, data, msg}）。

- code：HTTP 状态码（200 成功；4xx/5xx 对应错误，表现指定接口的失败特性）
- success：是否成功（code < 400 为 True）
- data：业务数据（失败时为 null 或附加信息）
- msg：提示语（成功默认「操作成功」，失败为具体原因）

仅用于非流式 JSON 接口；SSE 流式接口维持事件协议（见 ApiEnvelopeMiddleware）。
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BaseResult(BaseModel, Generic[T]):
    """统一响应信封。"""

    code: int = Field(200, description="HTTP 状态码")
    success: bool = Field(True, description="是否成功")
    data: T | None = Field(default=None, description="业务数据")
    msg: str = Field(default="操作成功", description="提示语")

    @classmethod
    def ok(cls, data: T | None = None, *, msg: str = "操作成功") -> "BaseResult[T]":
        """成功响应（code=200）。"""
        return cls(code=200, success=True, data=data, msg=msg)

    @classmethod
    def fail(cls, code: int = 400, *, msg: str = "操作失败", data: T | None = None) -> "BaseResult[T]":
        """失败响应（code 取 HTTP 状态码）。"""
        return cls(code=code, success=False, data=data, msg=msg)

    @classmethod
    def from_http_exception(cls, status_code: int, detail) -> "BaseResult[None]":
        """把 HTTPException / 校验错误的 detail 映射为信封（code=HTTP 状态码，msg=detail）。"""
        if isinstance(detail, str):
            msg = detail
        elif isinstance(detail, list):
            parts = [str(d.get("msg", d)) for d in detail if isinstance(d, dict)]
            msg = "; ".join(parts) or "参数校验失败"
        else:
            msg = str(detail or "请求失败")
        return cls.fail(status_code, msg=msg)


def is_base_result(payload: object) -> bool:
    """判断响应体是否已是 BaseResult 信封（避免二次封装）。"""
    return isinstance(payload, dict) and {"code", "success", "data", "msg"} <= set(payload)
