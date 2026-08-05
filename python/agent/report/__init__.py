"""
v2 成绩单报告智能体（Report Subagent）预留包 — Phase 2 实现

当前状态：空包（骨架预留）。

Phase 2 目标：
  实现成绩统计智能体，对应 /report 端点。核心功能：

  1. 输入：每科 Excel（multipart/form-data，文件名=科目）
  2. 流程：
     a. 每科 Excel →（LLM 或 openpyxl 提炼）单科学生 JSON
     b. 整合以学生为单位 JSON
     c. 遍历每学生：Python 算加权（展示性×30% + 考试性×70%）
     d. 填 1.html 模板（Jinja2）
     e. WeasyPrint 渲染 PDF
     f. 每学生独有 PDF 下载链接（MinIO presigned URL）
  3. 成绩记载功能：score JSON → 进步/突出/排名/最优成绩 comment
  4. 流式评价叙述：AI 对话中流式述说每个学生的评价

架构决策：
  - 复合统计用 Python 算（pandas），不用 LLM（防幻觉）
  - LLM 只产文本段（评价叙述），数值引用文件不记忆
  - 中间产物（单科 JSON、学生 JSON、加权 stats）落盘到 deepagents 文件系统
  - 选课建议步骤：调 recommend_courses tool（共享 tool，非独立实现）
  - 对话与 /evaluation 不共享

参考文档：
  - docs/v2.0.0/notes/2026-07-27-设计决策问答记录.md 决策 5
  - docs/v2.0.0/notes/2026-07-28-设计决策补充说明.md 决策 5 修订
"""