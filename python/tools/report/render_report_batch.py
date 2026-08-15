# -*- coding: utf-8 -*-
"""report 批量执行工具 — A-shell 的确定性管线（async，进度 channel，可取消）。

管线：解析合并 → 完整性断言 → Journal → 逐学生（并发 4）：
  LLM 填表（校验失败→Jinja2 降级）→ 综合评语（失败留空）→ PDF 渲染（失败→HTML 兜底）
  → 存储（MinIO/本地）→ report_artifacts 落库 → 进度 channel 事件
取消：每学生循环前检查 cancelled；CancelledError 收敛并清理中间产物。

file_keys 与进度 channel 从请求上下文注入（ContextVar，见 service.py）。
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.report.contract import ERR_RENDER_FAILED, ERR_UPLOAD_FAILED
from tools.report.fill_report_html import FillValidationError, fill_one_llm, fill_with_jinja2, get_template
from tools.report.generate_subjective_eval import generate_subjective_eval
from tools.report.merge_students import assert_integrity, journal_save, merge_files
from tools.report.parse_score_excels import ExcelParseError, parse_workbook

logger = logging.getLogger(__name__)

# 请求上下文：文件路径列表 + 进度 channel + 模板名（service 注入）
report_files_ctx: contextvars.ContextVar[list[str]] = contextvars.ContextVar("report_files", default=[])
report_progress_ctx: contextvars.ContextVar["asyncio.Queue"] = contextvars.ContextVar(
    "report_progress", default=None  # type: ignore[arg-type]
)
report_template_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("report_template", default="grade4-6.html")

# 年级分类规则兜底（LLM 分类失败/非法时使用）
DAOFA_SUBJECTS = {"道法", "道德与法治"}


def classify_by_rules(summary: dict) -> int | None:
    """规则兜底分类：摘要含道法 → 2；含必选/自选特征列 → 1；否则 None（需澄清）。"""
    files = summary.get("files", [])
    if not files:
        return None
    any_daofa = any(f.get("has_daofa") for f in files)
    any_ro = any(f.get("has_required_optional") for f in files)
    if any_daofa:
        return 2
    if any_ro and not any_daofa:
        return 1
    return None


async def _put(event: str, data: dict) -> None:
    """进度事件入 channel（无 channel 时静默）。"""
    q = report_progress_ctx.get()
    if q is not None:
        try:
            q.put_nowait((event, data))
        except Exception:  # noqa: BLE001
            pass


def render_pdf_sync(html: str) -> bytes | None:
    """WeasyPrint 渲染 PDF；缺系统依赖/失败 → None（走 HTML 兜底）。"""
    try:
        from weasyprint import HTML

        return HTML(string=html).write_pdf()
    except Exception as exc:  # noqa: BLE001
        logger.warning("weasyprint render failed, fallback html: %s", exc)
        return None


class RenderReportBatchInput(BaseModel):
    """render_report_batch 工具输入参数（file_keys 从请求上下文注入）。"""

    category: int = Field(..., description="年级分类：1=一二三年级（无道法），2=四五六年级（有道法）", ge=1, le=2)
    semester: str = Field(default="", description="学期（如 2023-2024第二学期）")


@tool(args_schema=RenderReportBatchInput)
async def render_report_batch(category: int, semester: str = "") -> dict:
    """批量生成学生成绩单（确定性管线；进度经 channel 上报；返回逐学生结果）。"""
    from agent import runtime

    file_keys = list(report_files_ctx.get() or [])
    if not file_keys:
        return _result([], [], ["未收到文件"])
    template_name = report_template_ctx.get() or ("grade1-3.html" if category == 1 else "grade4-6.html")

    # ── 1) 解析 + 合并 + 断言 + Journal ──────────────────────────────
    await _put("progress", {"phase": "parsing", "detail": f"{len(file_keys)} 个文件"})
    parsed = []
    for fp in file_keys:
        try:
            parsed.append(parse_workbook(fp))
        except ExcelParseError as exc:
            return _result([], [], [f"解析失败 {Path(fp).name}: {exc.reason}"], "error")
    merged = merge_files(parsed, semester=semester)
    integrity_errors = assert_integrity(merged, len(file_keys))
    if integrity_errors:
        return _result([], [], integrity_errors[:10], merged.batch_id)
    batch_dir = _batch_dir(merged.batch_id)
    journal_save(batch_dir / "intermediate", merged)
    await _put("progress", {"phase": "parsing", "detail": f"{len(merged.students)} 名学生"})

    # ── 2) 逐学生：填表 → 评语 → 渲染 → 存储 → 落库 ──────────────────
    template_html = get_template(template_name)
    students: list[dict] = []
    failed: list[dict] = []
    sem = asyncio.Semaphore(_concurrency())
    to_thread = asyncio.to_thread

    async def _per_student(stu: dict, idx: int) -> None:
        async with sem:
            if asyncio.current_task() and asyncio.current_task().cancelled():
                return
            sid = stu.get("student_id", f"stu{idx}")
            name = stu.get("name", sid)
            t0 = time.perf_counter()
            try:
                # 填表：LLM 主路 → Jinja2 降级
                html = None
                fill_error = None
                try:
                    html = await asyncio.wait_for(fill_one_llm(template_html, stu), timeout=60.0)
                except (FillValidationError, Exception) as exc:  # noqa: BLE001
                    fill_error = str(exc)[:200]
                if html is None:
                    html = fill_with_jinja2(template_html, stu)
                # 综合评语（失败留空不阻塞）
                comment = await generate_subjective_eval(stu)
                if comment:
                    html = html.replace('data-slot="comment"></p>', f'data-slot="comment">{comment}</p>')
                # 渲染：PDF 主路 → HTML 兜底
                pdf = await to_thread(render_pdf_sync, html)
                fmt = "pdf" if pdf is not None else "html"
                payload = pdf if pdf is not None else html.encode("utf-8")
                content_type = "application/pdf" if fmt == "pdf" else "text/html; charset=utf-8"
                file_key = f"{merged.batch_id}/{sid}.{fmt}"
                minio_repo = _minio_repo()
                try:
                    minio_repo.upload(file_key, payload, content_type=content_type)
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(f"{ERR_UPLOAD_FAILED}: {exc}") from exc
                # 落库
                try:
                    runtime.report_artifact_repo.create_artifact(
                        batch_id=merged.batch_id,
                        student_id=sid,
                        student_name=name,
                        format=fmt,
                        status="ok",
                        file_key=file_key,
                        error_code=fill_error and "fill_failed" or None,
                        error_message=fill_error,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("artifact repo write failed: %s", exc)
                students.append(
                    {"student_id": sid, "name": name, "status": "ok", "format": fmt, "file_key": file_key}
                )
                await _put("student_done", {"student_id": sid, "name": name, "status": "ok", "format": fmt, "url": ""})
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                failed.append(
                    {
                        "student_id": sid,
                        "name": name,
                        "code": ERR_RENDER_FAILED,
                        "reason": str(exc)[:200],
                    }
                )
                await _put("student_error", {"student_id": sid, "name": name, "code": ERR_RENDER_FAILED, "reason": str(exc)[:200]})
            finally:
                logger.debug("student processed %s %.1fs", name, time.perf_counter() - t0)

    try:
        await asyncio.gather(*[_per_student(s, i) for i, s in enumerate(merged.students)])
    except asyncio.CancelledError:
        logger.info("render_report_batch cancelled, batch=%s", merged.batch_id)
        raise

    result = _result(students, failed, merged.warnings, merged.batch_id)
    await _put("batch_done", result)
    return result


def _result(students: list[dict], failed: list[dict], warnings: list[str], batch_id: str) -> dict:
    return {
        "batch_id": batch_id,
        "students": students,
        "failed_students": failed,
        "warnings": warnings,
        "summary": {"total": len(students) + len(failed), "ok": len(students), "failed": len(failed)},
    }


def _batch_dir(batch_id: str) -> Path:
    root = Path(__file__).resolve().parent.parent.parent / ".documents" / "reports"
    return root / batch_id


def _concurrency() -> int:
    from config import get_settings

    return get_settings().report_llm_fill_concurrency


def _minio_repo():
    from agent import runtime

    return runtime.minio_repo
