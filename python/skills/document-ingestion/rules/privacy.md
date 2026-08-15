# Rules: privacy（隐私与隔离）

1. 个人文档（成绩单等）摄入后归属 user 分区（Milvus user_id 隔离），脱敏后入库（姓名/学号/班级/日期）。
2. 个人文档仅所有者可检索（query_knowledge 强过滤 user 分区）。
3. 结构化提取（课程/学分/成绩）写入 metadata_json，仅快照工具按 user 读取。
