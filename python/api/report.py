"""v2 成绩单报告路由 — Phase 2 实现

当前状态：路由骨架预留。

Phase 2 实现目标：
  POST /report
    请求：multipart/form-data
      files: list[UploadFile]  — 每科 Excel（文件名=科目）
      semester: str            — 学期（可选）
    响应：SSE 流式
      event: progress  — 解析中/统计中/渲染中
      event: result    — {students: [{student_id, name, pdf_url}], summary}
      pdf_url = MinIO presigned URL（每学生独有链接）

  实现参考：
    from fastapi import APIRouter, UploadFile
    from fastapi.responses import StreamingResponse

    router = APIRouter()

    @router.post("/report")
    async def report(files: list[UploadFile], semester: str = ""):
        # 委派 report subagent
        ...
        return StreamingResponse(...)

架构决策：
  - 调用 app/report/ 下的 report subagent（非此文件实现业务逻辑）
  - 此文件只做路由注册 + 参数校验 + 响应格式转换
  - SSE 流式响应，复用 v1 的 stream_token_markup_parser 模式
"""
from fastapi import APIRouter

router = APIRouter()