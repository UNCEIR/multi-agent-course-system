# Command: render-batch（批量生成）

## Steps
1. 调用 `render_report_batch(category, semester)` 生成全部学生成绩单（file_keys 由系统注入）。
2. 管线内部：解析合并 → 完整性断言 → Journal 落盘 → 逐学生填表/评语/渲染/存储/落库。
3. 接收进度事件：`progress` / `student_done` / `student_error`。
4. 收齐 `done` 后呈现：成功学生下载链接列表 + 失败明细 + 警告清单。
