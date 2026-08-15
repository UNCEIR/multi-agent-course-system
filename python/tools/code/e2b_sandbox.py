# -*- coding: utf-8 -*-
"""E2B 代码执行内核 — e2b Python SDK（AsyncSandbox）直连。

- 模块级 sandbox 单例复用（懒创建；异常 → 清缓存下次重建；每次执行后 set_timeout 保活刷新）
- asyncio 锁串行执行（单沙箱避免并发状态污染）
- 返回统一 dict：{stdout, stderr, exit_code, source:"e2b"}；失败 → isError 结构化（不抛）

SDK 轮子参考：AsyncSandbox.create / commands.run / set_timeout / kill
（AsyncTemplate.add_mcp_server 为模板构建期函数，运行时执行代码无需模板。）
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = ("python", "javascript", "bash")

_sandbox: object | None = None
_lock: asyncio.Lock | None = None
_killed: bool = False  # 测试可置 True 强制重建


def command_for(language: str, code: str) -> tuple[str | None, str | None]:
    """语言 → (写入沙箱的文件名, 执行命令)。返回 (None, None) 表示不支持。

    多行代码写文件执行（python3 -c 会被 shell 转义换行，无法承载多行源码）。
    """
    if language == "python":
        return "tmp_exec.py", "python3 /home/user/tmp_exec.py"
    if language == "javascript":
        return "tmp_exec.js", "node /home/user/tmp_exec.js"
    if language == "bash":
        return None, code
    return None, None


async def _create_sandbox() -> object:
    from e2b import AsyncSandbox
    from config import get_settings

    timeout = get_settings().e2b_sandbox_timeout
    return await AsyncSandbox.create(timeout=timeout, allow_internet_access=True)


async def get_sandbox() -> object:
    """获取（或创建）E2B sandbox 单例；失败 → 清缓存下次重建（不抛）。"""
    global _sandbox, _lock, _killed
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if _sandbox is not None and not _killed:
            return _sandbox
        try:
            _sandbox = await _create_sandbox()
            _killed = False
            logger.info("e2b sandbox created: %s", getattr(_sandbox, "sandbox_id", "?"))
        except Exception as exc:  # noqa: BLE001
            _sandbox = None
            logger.warning("e2b sandbox create failed: %s", exc)
            raise
        return _sandbox


async def run_code(language: str, code: str, timeout: int = 30) -> dict:
    """在 E2B 云沙箱中执行代码，返回 {stdout, stderr, exit_code, source} 或 isError。"""
    file_name, cmd = command_for(language, code)
    if cmd is None:
        return {
            "isError": True,
            "code": "E2B_UNSUPPORTED_LANGUAGE",
            "message": f"e2b 支持语言：{', '.join(SUPPORTED_LANGUAGES)}",
        }
    try:
        sandbox = await get_sandbox()
        from config import get_settings

        try:
            await sandbox.set_timeout(get_settings().e2b_sandbox_timeout)
        except Exception:  # noqa: BLE001
            pass  # 保活刷新失败不阻断执行
        if file_name is not None:
            await sandbox.files.write(f"/home/user/{file_name}", code)
        # 前台模式：run 直接返回 CommandResult；非 0 退出抛 CommandExitException（result 在其上）
        result = await sandbox.commands.run(cmd, timeout=timeout)
        return {
            "stdout": str(getattr(result, "stdout", "") or "")[:4000],
            "stderr": str(getattr(result, "stderr", "") or "")[:2000],
            "exit_code": getattr(result, "exit_code", 0),
            "source": "e2b",
        }
    except Exception as exc:  # noqa: BLE001
        # CommandExitException（非 0 退出）：stdout/stderr/exit_code 直接挂在异常上
        if getattr(exc, "exit_code", None) is not None:
            return {
                "stdout": str(getattr(exc, "stdout", "") or "")[:4000],
                "stderr": str(getattr(exc, "stderr", "") or "")[:2000],
                "exit_code": int(getattr(exc, "exit_code", 1)),
                "source": "e2b",
            }
        # 连接/超时类错误 → 重建 sandbox 保后续可用
        _reset()
        return {"isError": True, "code": "E2B_EXECUTION_FAILED", "message": str(exc)[:200]}


def _reset() -> None:
    """清空 sandbox 缓存（失败/测试重建入口）。"""
    global _sandbox, _killed
    sandbox = _sandbox
    _sandbox = None
    _killed = False
    if sandbox is not None:
        try:
            asyncio.get_event_loop().create_task(_safe_kill(sandbox))
        except Exception:  # noqa: BLE001
            pass


async def _safe_kill(sandbox: object) -> None:
    try:
        await sandbox.kill()
    except Exception:  # noqa: BLE001
        pass


async def close() -> None:
    """关闭 sandbox（进程退出/测试清理用）。"""
    global _sandbox
    sandbox = _sandbox
    _sandbox = None
    if sandbox is not None:
        await _safe_kill(sandbox)
