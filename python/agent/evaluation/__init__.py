"""
v2 评价寄语智能体（Evaluation Agent）预留包 — Phase 2 实现

当前状态：空包（骨架预留）。

Phase 2 目标：
  实现评价寄语 agent，对应 /evaluation 端点。核心功能：

  1. 输入：studentList JSON（POST /evaluation body）
     - studentId, studentName, comment_type, teacherSubjectiveEvaluation, scoreList[]

  2. comment_type 四种：
     - 赞扬鼓励型：肯定成绩+鼓励继续努力
     - 客观评价型：理性分析优劣势
     - 温情关怀型：体现对学生的关心
     - 幽默风趣型：轻松幽默的语气

  3. 输出：{studentId, studentName, comment}
     - comment 结合 comment_type + teacherSubjectiveEvaluation + scoreList 生成
     - score 数值是输入，LLM 不自算（防幻觉）

  4. 流式：评语逐 token 流式输出（SSE）

架构决策：
  - 独立端点 /evaluation，与 /report 对话不共享
  - 前端两个不同 agent 页面
  - LLM 只做文本生成，数值引用文件不记忆
  - score JSON 落盘（deepagents 文件系统），LLM 读文件生成 comment

参考文档：
  - docs/v2.0.0/notes/2026-07-28-设计决策补充说明.md 智能体重构
  - docs/v2.0.0/image.png（教师寄语→大学生成绩评语参考）
"""