"""v2 评价寄语路由 — Phase 2 实现

当前状态：路由骨架预留。

Phase 2 实现目标：
  POST /evaluation
    请求：application/json
      body: list[StudentEvaluationInput]
        StudentEvaluationInput:
          studentId: str
          studentName: str
          comment_type: Literal["赞扬鼓励型", "客观评价型", "温情关怀型", "幽默风趣型"]
          teacherSubjectiveEvaluation: str
          scoreList: list[ScoreItem]
            ScoreItem:
              testTime: str
              testName: str
              subjectScores: list[SubjectScore]
                SubjectScore:
                  testType: str
                  testName: str
                  testSubject: str
                  testAverageScore: float
                  studentRank: int
                  studentScore: float
                  fullScore: float
    响应：SSE 流式
      event: comment_token  — 逐 token 评语
      event: result         — {studentId, studentName, comment}

  实现参考：
    router = APIRouter()

    @router.post("/evaluation")
    async def evaluation(body: list[dict]):
        # 委派 evaluation subagent
        ...
        return StreamingResponse(...)

架构决策：
  - 调用 app/evaluation/ 下的 evaluation agent
  - 此文件只做路由注册 + 参数校验 + 响应格式转换
  - score 数值是输入字段，LLM 不自算（防幻觉）
"""
from fastapi import APIRouter

router = APIRouter()