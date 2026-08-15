# eval_sets — 评估数据集规范 v2（对齐 RAGAS / LangSmith / DeepEval / Promptfoo）

> 本目录是 v2.0.0 端到端评估体系的**数据集层**。规范 v2 学习业界主流评测设计：
> RAGAS 四指标（context precision/recall、faithfulness、answer relevancy）、
> LangSmith Dataset 的 inputs/outputs/reference 三分量 + evaluator 分层、
> DeepEval 的 golden 结构（input/actual/expected/context）、
> Promptfoo 的断言分类与权重。Phase 2 落地**断言式 + 检索式**指标；
> LLM-as-judge（faithfulness/answer relevancy/rubric）接口预留，Phase 4 全量实施。

## 1. 文件格式与字段契约

每行一个 case 的 JSONL。字段分层（标 `*` 为必填）：

```json
{
  "case_id": "intent_01",
  "type": "chat_intent",                    // * 归属评测集（registry 索引）
  "scenario": "选课推荐",                    // 业务场景中文名
  "difficulty": "easy",                     // easy | medium | hard（难度分层，便于分档报告）
  "description": "学生想选不用考试的课",
  "input": {                                 // * 请求输入（对齐 LangSmith inputs）
    "message": "...",
    "user_id": "..."                         // 可选：需要身份注入的用例
  },
  "expected": {                              // * 期望行为（对齐 DeepEval golden）
    "intent": "recommend",                   // 意图标签
    "tool_chain": ["recommend_courses"],     // 期望工具调用链
    "route": "main_agent"                    // 期望路由
  },
  "reference": {                             // 参考标准（对齐 LangSmith reference / RAGAS goldens）
    "answer": "理想回答要点...",              // 理想回答（LLM-as-judge 用）
    "contexts": ["应被引用的知识片段"],        // 参考上下文（context recall 计算用）
    "keywords": ["不用考试", "推荐"]          // 断言式关键词（OR 语义）
  },
  "judge": {                                 // 评估器声明（对齐 Promptfoo assert 分类）
    "metric": "tool_chain",                  // tool_chain | numeric | reference | recall | faithfulness | answer_relevancy | rubric
    "mode": "exact",                         // exact(确定性) | code(脚本) | llm(Phase 4)
    "rubric": "评分标准文本（mode=llm 时必填）",
    "threshold": 1.0                         // 通过阈值（0-1）
  },
  "assertions": [                            // 确定性断言（可多个，权重求和）
    {"kind": "contains", "field": "reply", "value": "不用考试", "weight": 1.0},
    {"kind": "not_contains", "field": "reply", "value": "编造的引用"},
    {"kind": "numeric", "field": "derived.weighted_avg", "value": 85.8, "tolerance": 0.1}
  ],
  "metadata": {"source": "handcrafted", "created_at": "2026-08-13"}
}
```

## 2. 指标矩阵与评估器分层

| 指标 | 定义 | 采集 | mode | Phase |
|------|------|------|------|------|
| tool_chain 命中率 | 期望工具调用链 == 实际 | trace tool 事件 | exact | 2 |
| 意图识别准确率 | 期望 intent == 实际 | trace LLM 路由 | exact | 2 |
| numeric 正确率 | 确定性计算 vs 手算 | 断言 | exact | 2 |
| reference 数值核验 | 输出数字 ∈ 数据源 | 代码核验闸 | code | 2 |
| recall@k | 应命中 chunk 是否在 top-k | 检索结果 | code | 2 |
| **context recall** | 参考上下文被检索召回比例 | reference.contexts vs hits | code | 2（检索集） |
| **context precision** | 检索命中中相关片段占比 | 同上 | code | 2（检索集） |
| faithfulness | 回答陈述均可由检索片段支持 | LLM-as-judge 逐句核对 | llm | 4 |
| answer_relevancy | 回答与问题的相关完整性 | LLM-as-judge | llm | 4 |
| rubric 分 | 按评分标准打分（G-Eval 风格） | LLM-as-judge | llm | 4 |
| 端到端延迟 P50/P95 | 各端点耗时分布 | runner 计时 | code | 2 |

评估器分层（对齐 LangSmith evaluator 类型）：
1. **exact/code（Phase 2 可跑）**：确定性断言、正则、数值比对、检索交集——不依赖 LLM，可回归
2. **llm（Phase 4 全量）**：faithfulness / answer_relevancy / rubric 打分——依赖 `judge.metric` + `judge.rubric`，runner 预留 `--judge` 开关

## 3. 数据集 Registry

| 集 | type | 主要指标 | 数据来源 |
|----|------|---------|---------|
| chat_intent.jsonl | chat_intent | tool_chain 命中 / 意图准确率 | 手写 20 条（四智能体 + 插件场景） |
| report_math.jsonl | report_math | numeric 正确率 / reference | 真实样本派生 |
| evaluation_comment.jsonl | evaluation_comment | reference 数值核验 / faithfulness(4) | 真实成绩单派生 |
| kb_retrieval.jsonl | kb_retrieval | recall@k / context precision·recall | 手册真实 chunk 标注 |

## 4. 运行与报告

```bash
cd python && python eval/runner.py --set <name>            # 断言式（Phase 2）
cd python && python eval/runner.py --set <name> --judge    # 追加 LLM-as-judge（Phase 4）
cd python && python scripts/import_langsmith_dataset.py --set <name>
```

报告输出 `eval/reports/<set>-<date>.json`：
- 逐 case：pass / 各指标分 / 延迟 / LangSmith run_id 回链（live）
- 汇总：通过率、recall@k、context recall/precision、延迟 P50/P95、按 difficulty 分档

## 5. 新增评测集规范

1. 先定 `type` 与指标集（registry 加一行）
2. 每 case 必须带 `expected` 与至少一个 `judge` 或 `assertions`
3. 检索类 case 必须带 `reference.contexts`（否则 context 指标不可算）
4. LLM-as-judge 类 case 必须带 `reference.answer` + `judge.rubric`
5. `case_id` 全局唯一（`<type>_<seq>`）
