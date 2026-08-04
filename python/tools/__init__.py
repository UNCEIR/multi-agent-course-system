"""
v2 工具实现预留包 — Phase 1 实现

当前状态：空包（骨架预留）。

Phase 1 目标：
  在此目录下实现 v2 的各工具（tool），用 Pydantic schema 定义输入输出，
  通过 ToolRegistry 统一注册。工具分为两类：

  1. 确定性工具（Python 逻辑，不走 LLM）：
     - compute_weighted_grade：加权复合统计（展示性评价×30% + 考试性评价×70%）
     - transcript_parser：Excel 成绩单解析（openpyxl / LLM 提炼）
     - report_renderer：Jinja2 HTML → WeasyPrint PDF 渲染

  2. LLM 增强工具（调用 LLM 但数值引文件）：
     - evaluation_generator：按 comment_type 生成评语
     - query_knowledge：FastGPT KB Q&A 检索（经 MCP 调用）

注册模式：
  from langchain_core.tools import tool
  from pydantic import BaseModel, Field

  class WeightedGradeInput(BaseModel):
      display_eval: float = Field(description="展示性评价分数")
      exam_eval: float = Field(description="考试性评价分数")

  @tool(args_schema=WeightedGradeInput)
  def compute_weighted_grade(display_eval: float, exam_eval: float) -> float:
      \"\"\"计算加权期末总评。\"\"\"
      return display_eval * 0.3 + exam_eval * 0.7

架构决策：
  - 每个工具一个文件，通过 tools/__init__.py 统一导出
  - 工具用 @tool 装饰器 + Pydantic args_schema，LangChain 自动生成 JSON Schema
  - 与 v1 agent（app/recommend/agents/）无关，v1 的 agent 是编排层，工具是原子能力
"""