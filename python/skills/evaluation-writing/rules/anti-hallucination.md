# Rules: anti-hallucination（反幻觉硬约束）

1. **数值引用硬闸**：评语中每个数字必须来自快照/雷达数据（容差 0.5），违规回灌重试一次，仍失败走规则化评语，**绝不空返回**。
2. **LLM 给不出任何数字**：雷达数值由代码按 metric 枚举计算（weighted_gpa/stability/top_subject/pass_rate/credit_load），维度提案只命名与赋权。
3. **维度提案硬校验**：维度数必须恰为 5、权重合计≈1、metric 必须为代码枚举；非法 → 回灌重试 → 默认维度集。
4. **无成绩单数据**：快照返回 `no_transcript_data` 时明确报错，不空跑 LLM。
5. **身份隔离**：学生端只能读取本人评价（显式 user_id 过滤）；教师端生成需显式目标学生。
