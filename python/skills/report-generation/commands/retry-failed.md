# Command: retry-failed（失败重试）

## Steps
1. `done` 事件携带 `failed_students`（student_id + 原因码）与 `warnings`。
2. 对失败学生向用户说明原因（解析失败/填表失败/渲染失败/上传失败）。
3. 用户可要求对失败学生单独重试（重新提交或指定学生）。
4. 失败隔离：部分失败不影响已成功学生（共享 fallback 规则）。
