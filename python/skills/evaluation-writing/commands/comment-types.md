# Command: comment-types（评语类型）

## 四种类型（显式必选）
- `semester_summary`：学期总结——平稳客观，整体学业表现
- `encouragement`：鼓励寄语——温暖鼓励，展望下学期
- `improvement_advice`：改进建议——建设性，弱项提升路径
- `recommendation`：升学/就业推荐——积极推荐，突出潜力

## 规则
1. 用户未指定类型时**先询问**，不默认代选。
2. 非法类型 → 422 结构化错误（合法类型列表给出）。
