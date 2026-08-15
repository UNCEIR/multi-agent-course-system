# -*- coding: utf-8 -*-
"""e2b_sandbox 内核单测（mock e2b SDK，不真连）。"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, ".")
from tools.code import e2b_sandbox  # noqa: E402


class FakeResult:
    def __init__(self, stdout="", stderr="", exit_code=0):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code


class FakeHandle:
    """兼容层：前台 run 直接返回 result，异常路径 raise。"""

    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    async def wait(self):
        if self._exc is not None:
            raise self._exc
        return self._result


class FakeSandbox:
    def __init__(self):
        self.sandbox_id = "fake-sbx"
        self.killed = False
        self.timeouts = []
        self.written = []
        self.run_exc: Exception | None = None

    async def set_timeout(self, timeout):
        self.timeouts.append(timeout)

    async def kill(self):
        self.killed = True

    async def _fake_write(self, path, data):
        self.written.append((path, data))

    async def _fake_run(self, cmd, timeout):
        if self.run_exc is not None:
            raise self.run_exc
        return self.run_result


def make_sandbox(result=None, exc=None):
    sbx = FakeSandbox()
    sbx.run_result = result
    sbx.run_exc = exc
    sbx.commands = SimpleNamespace(run=sbx._fake_run)
    sbx.files = SimpleNamespace(write=sbx._fake_write)
    return sbx


@pytest.fixture(autouse=True)
def reset_singleton():
    e2b_sandbox._sandbox = None
    e2b_sandbox._lock = None
    e2b_sandbox._killed = False
    yield
    e2b_sandbox._sandbox = None
    e2b_sandbox._lock = None
    e2b_sandbox._killed = False


def test_command_mapping():
    assert e2b_sandbox.command_for("python", "print(1)") == ("tmp_exec.py", "python3 /home/user/tmp_exec.py")
    assert e2b_sandbox.command_for("javascript", "console.log(1)") == ("tmp_exec.js", "node /home/user/tmp_exec.js")
    assert e2b_sandbox.command_for("bash", "echo hi") == (None, "echo hi")
    assert e2b_sandbox.command_for("ruby", "x") == (None, None)


@pytest.mark.asyncio
async def test_run_code_success(mocker):
    sbx = make_sandbox(result=FakeResult(stdout="4\n", stderr="", exit_code=0))
    mocker.patch("tools.code.e2b_sandbox._create_sandbox", new_callable=mocker.AsyncMock, return_value=sbx)
    out = await e2b_sandbox.run_code("python", "print(2+2)", timeout=10)
    assert out["stdout"] == "4\n"
    assert out["exit_code"] == 0
    assert out["source"] == "e2b"
    assert sbx.timeouts == [300]
    assert sbx.written == [("/home/user/tmp_exec.py", "print(2+2)")]


@pytest.mark.asyncio
async def test_run_code_nonzero_exit(mocker):
    class CommandExit(Exception):
        def __init__(self):
            self.stdout = ""
            self.stderr = "boom"
            self.exit_code = 1

    sbx = make_sandbox(exc=CommandExit())
    mocker.patch("tools.code.e2b_sandbox._create_sandbox", new_callable=mocker.AsyncMock, return_value=sbx)
    out = await e2b_sandbox.run_code("python", "1/0")
    assert out["exit_code"] == 1
    assert "boom" in out["stderr"]


@pytest.mark.asyncio
async def test_run_code_connection_failure_resets_sandbox(mocker):
    first = make_sandbox(exc=RuntimeError("connection lost"))
    second = make_sandbox(result=FakeResult(stdout="ok\n", exit_code=0))
    mocker.patch(
        "tools.code.e2b_sandbox._create_sandbox",
        new_callable=mocker.AsyncMock,
        side_effect=[first, second],
    )
    out1 = await e2b_sandbox.run_code("bash", "echo x")
    assert out1["isError"] is True
    assert out1["code"] == "E2B_EXECUTION_FAILED"
    out2 = await e2b_sandbox.run_code("bash", "echo y")
    assert out2["source"] == "e2b"
    assert out2["stdout"] == "ok\n"


@pytest.mark.asyncio
async def test_run_code_unsupported_language():
    out = await e2b_sandbox.run_code("ruby", "puts 1")
    assert out["isError"] is True
    assert out["code"] == "E2B_UNSUPPORTED_LANGUAGE"


@pytest.mark.asyncio
async def test_sandbox_reuse(mocker):
    sbx = make_sandbox(result=FakeResult(stdout="1\n"))
    create = mocker.patch("tools.code.e2b_sandbox._create_sandbox", new_callable=mocker.AsyncMock, return_value=sbx)
    await e2b_sandbox.run_code("python", "a=1")
    await e2b_sandbox.run_code("python", "b=2")
    create.assert_called_once()


@pytest.mark.asyncio
async def test_close_kills_sandbox(mocker):
    sbx = make_sandbox(result=FakeResult(stdout="1\n"))
    mocker.patch("tools.code.e2b_sandbox._create_sandbox", new_callable=mocker.AsyncMock, return_value=sbx)
    await e2b_sandbox.get_sandbox()
    await e2b_sandbox.close()
    assert sbx.killed is True
    assert e2b_sandbox._sandbox is None
