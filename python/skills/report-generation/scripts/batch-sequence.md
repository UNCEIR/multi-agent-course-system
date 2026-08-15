# Script: batch-sequence（批量成绩单编排序列示例）

> 编排契约示例；单工具参数以工具 docstring 为准。

## 两步编排
```json
[{"tool": "inspect_score_excels", "args": {}},
 {"tool": "render_report_batch", "args": {"category": 2, "semester": "2023-2024第二学期"}}]
```
- file_keys 由请求上下文注入，工具无需传文件路径。
- `category` 由 LLM 依据摘要决策；规则兜底：含道法→2，含必选/自选→1。

## 事件流（SSE）
`text / tool / progress / student_done / student_error / done`
done 负载 = 工具结果（学生链接 + 失败明细 + 警告），不采信 LLM 文本。

## 降级链
LLM 填表失败 → Jinja2 确定性填充；WeasyPrint 失败 → HTML；MinIO 失败 → 本地兜底。
