# Command: inspect-classify（摘要与年级分类）

## Steps
1. 调用 `inspect_score_excels`（file_keys 由系统注入）查看文件摘要：学科/班级/是否含道法列/是否含必选-自选特征列/学生数。
2. 按摘要判断年级分类（LLM 决策）：
   - `category=1`：一二三年级（无道法成绩表）
   - `category=2`：四五六年级（有道法成绩表）
3. 摘要不足以判断且用户未提供年级信息 → **向用户澄清**，不要硬猜。
