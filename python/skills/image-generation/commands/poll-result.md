# Command: submit-task（提交生成任务）

## Steps
1. 确认参数：`prompt`（必填，主体/场景/风格；组图明确 1-3 张）、`ratio`、`style`、`negative_prompt`、`scale`（默认 0.7）、`force_single`（默认 false）
2. 调用 `image_generate` 提交任务 → 返回 `{task_id, status: "in_queue", hint}`
3. **立即进入查询流程**（见 poll-result），不得在此结束对话或声称已生成

# Command: poll-result（轮询查询结果）

## Steps
1. 调用 `image_generate_get(task_id, attempt)` 查询：
   - `status=done` → 转存完成，展示 `image_urls`（持久化链接）给用户
   - `status=in_queue/generating` → 按 `next_poll_after_seconds` 等待后再次查询（attempt+1）
   - `status=not_found/expired` → 结构化错误，重新提交
   - `isError`（审核/限流）→ 按 `retryable` 决定重试或提示用户改 prompt
2. **轮询上限**：`attempts_left=0` 或已查询 10 次仍 generating → 告知用户"生成中，可稍后用 task_id 再查"，结束本次查询
3. **未 done 不伪造**：任何情况下不得虚构图片链接
