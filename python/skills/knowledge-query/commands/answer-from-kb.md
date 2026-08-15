# Command: answer-from-kb（检索与作答）

## Steps
1. 判断问题域：学校制度 / 课程修读 / 校园生活 / 个人学业 / 其他。
2. 调用 `query_knowledge(query, top_k=5)`（user_id 由系统注入，检索当前用户分区）。
3. 基于检索片段（content + 来源）组织回答，**引用来源**。
4. 检索为空 → 说明知识边界，不编造。
