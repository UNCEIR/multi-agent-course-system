# 硬/软约束分离重构

## 背景与问题

- **本轮要解决的问题**：原有编排把所有用户偏好都当软约束处理（仅影响排序分数），导致用户明确指定"东校区"时仍可能推出西校区的课程，推荐结果与用户硬性要求不符。
- **触发原因**：用户发现 CourseFeasibilityAgent 的 `_hard_conflicts()` 几乎只检查时间冲突，校区/分类/老师/考试方式等关键字段全部缺失过滤；CourseRerankAgent 打分写死（+0.5/-0.4），LLM 决策空间被挤压。
- **影响范围**：全链路推荐质量，尤其是用户有明确诉求的场景（指定校区、分类、老师）。

## 总体架构方案

### 涉及模块

| 文件 | 改动性质 |
|------|---------|
| `python/models/schemas.py` | 新增 `HardConstraints` Pydantic 模型；`StudentProfile` 增加 `hard_constraints` 字段 |
| `python/agents/student_profile_agent.py` | 重写 `SYSTEM_PROMPT`；新增 `_parse_hard_constraints()` |
| `python/orchestrator/hard_constraint_filter.py` | 新建：单一职责过滤器类 |
| `python/orchestrator/supervisor.py` | Phase 1.5 注入；`recommend()` 和 `stream_recommend()` 均更新 |
| `python/agents/course_feasibility_agent.py` | 清理冗余硬约束逻辑，软偏好警告降级为 `low` |
| `python/orchestrator/__init__.py` | 暴露 `HardConstraintFilter` |

### 数据流

```
Phase 1:   StudentProfileAgent (画像提取 + 硬约束识别) ∥ CourseRecallAgent (宽召回)
           ↓ 画像提取成功后 → 精细召回合并
Phase 1.5: HardConstraintFilter (确定性过滤) ← NEW
           违反硬约束的课程移除，稀疏时追加 warning
Phase 2:   CourseRerankAgent (软约束 LLM 排序) ∥ CourseFeasibilityAgent (容量警告)
Phase 3:   RecommendationReasonAgent (推荐理由)
```

### 关键设计取舍

- **两类硬约束**：天然硬（campus/avoid_time_slots/categories/teacher/no_exam，任何提及即触发）与强意图才升级为硬（no_group_work/max_difficulty/max_workload，需要"只/必须/一定"等强调词）。
- **警告不补充**：过滤后候选不足时只追加 `hard_constraint_sparse` warning，不强行放宽条件，由用户自主决策。
- **CourseFeasibilityAgent 职责收窄**：不再执行硬约束过滤，仅做容量告警和软偏好参考提示（level 降为 `low`）。

## 细节实现

### HardConstraints 模型

```python
class HardConstraints(BaseModel):
    campus: list[str] = []           # 天然硬：校区
    avoid_time_slots: list[str] = [] # 天然硬：避开时间
    categories: list[str] = []       # 天然硬：课程分类
    teacher: str = ""                # 天然硬：指定老师
    no_exam: bool = False            # 天然硬：不考试
    no_group_work: bool = False      # 强意图：不小组
    max_difficulty: str | None = None# 强意图：难度上限
    max_workload: str | None = None  # 强意图：作业量上限
```

### HardConstraintFilter 核心逻辑

`_check_violations()` 按字段逐一判断，有任何违规则该课程进入 `filtered_out` 列表，不进入重排。难度/作业量使用有序字典做上限比较（`低=0, 中=1, 高=2`）。

### StudentProfileAgent Prompt 变化

新 SYSTEM_PROMPT 在输出 JSON 中增加顶层 `hard_constraints` 字段，明确告知 LLM：
- 天然硬约束：只要提及具体值就填入（不需要强调词）
- 强意图才升级：仅当有"只要/必须/一定/绝对/不能/坚决"等词时才填

`_parse_hard_constraints()` 方法解析该字段并构造 `HardConstraints` 对象；启发式兜底路径 `_heuristic_profile()` 同步补充了硬约束提取逻辑。

### Supervisor 变化

```python
# Phase 1.5 — 新增
if student_profile and has_active_constraints(student_profile.hard_constraints):
    raw_courses, hc_filtered, hc_warnings = self.hard_constraint_filter.filter(
        raw_courses, student_profile.hard_constraints
    )
    warnings.extend(hc_warnings)
```

`warnings` 变量在 Phase 1.5 后初始化，Phase 2 的 feasibility warnings 通过 `extend` 合并（而非覆盖）。`stream_recommend()` 额外 yield 了 `phase15_complete` 事件供前端感知。

### AsyncGenerator 顺手修复

Supervisor 原有 `"AsyncGenerator"` 类型注解未导入（basedpyright warning），本次一并修复为 `from typing import AsyncGenerator`。

## Debug 结论

- **根因**：所有字段全部当软约束处理，没有确定性的过滤门槛；`_hard_conflicts()` 仅检查时间冲突但漏掉其他关键字段。
- **排查过程**：审查 `CourseFeasibilityAgent` 发现 `_hard_conflicts()` 只有 `avoid_time_slots` 判断；审查 `CourseRerankAgent` 发现打分硬编码导致 LLM 排序能力被边缘化。
- **解决方式**：在 Phase 1 与 Phase 2 之间插入确定性过滤层，LLM 只在通过硬过滤的子集上做软约束排序。

## 测试与验证

- **已执行**：`python -m pytest python/tests/ -m "not slow" -v`
- **结果**：35 passed, 1 deselected（deselected 是预期的 slow 标记测试）
- **编译检查**：`python -m compileall -q` 所有改动文件通过
- **未执行**：端到端 Docker 部署测试（需容器环境）；LLM 硬约束提取准确性的真实推理测试

## 经验与后续

- **经验**：LLM 提取的字段一定要在编排层加确定性 guard，不能完全依赖 LLM 的"推荐分数"来间接体现用户硬性需求——分数影响排序，但不能阻止违规结果进入推荐列表。
- **后续建议**：
  1. 为 `HardConstraintFilter` 单独补充单元测试（各字段过滤边界用例）
  2. 观察线上 `hard_constraint_filter.done` 日志中的 `filtered_out` 数量，评估 LLM 提取准确率
  3. 若发现漏提取（用户说了校区但 `hard_constraints.campus` 为空），可考虑在 `_heuristic_profile` 中补充更多规则兜底
  4. 前端可利用 `phase15_complete` SSE 事件展示"已过滤 X 门不符合要求的课程"提示
