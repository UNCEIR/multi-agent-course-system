# 知识库落库审计 + chat 知识库检验（PDF1 手册 / PDF2 成绩单）

## 背景与问题

- 用户要求核实两个 PDF 是否 100% 落库，并生成专门检验 chat 知识库的 JSON（成绩单本人权限 + 学生手册公共知识准确性）。
- 模型无法直接读取 PDF 内容，改用 MySQL/Milvus 实际数据 + 检索测试核实。

## 落库审计（数据库实测）

| PDF | Milvus document_chunks | MySQL document_records | 内容抽查 |
|---|---|---|---|
| 广东工业大学2025年学生手册.pdf | `public` **221 chunks** | `handbook_2025_e3595432` 221/ok | 休学待遇(第26/59条)、入伍保留学籍(第26条)、集会规定(第42条)、转专业(第42条)、注册手续(第9条) 均检索到 |
| 本科生中文成绩单(1860658).pdf | `3123003252` **3 chunks** | `transcript_6bc5abed` 3/ok | 学院/专业/班级/学号掩码/姓名脱敏、各学期成绩、总学分148.5/必修102/选修46.5 |

**向量升级**：此前是 `--embedding local` 占位向量（当时真实 embedding 额度不足）；额度恢复后重跑真实 `text-embedding-v4`：
- `python scripts/ingest_student_handbook.py`（221 chunks）
- `python scripts/ingest_transcript_desensitized.py --user-id 3123003252 --name 黄信烨`（3 chunks）

## 检验 JSON 与执行

新增（纯 JSON，供塞入 `/api/v1/chat` 逐条检验）：
- `python/scripts/kb_test_transcript.json`（成绩单：总分/成绩/GPA/班级 + 隐私脱敏 case）
- `python/scripts/kb_test_handbook.json`（手册：休学待遇/集会游行/入伍保留学籍/转专业/注册手续）
- 执行器：`python/scripts/run_kb_test.py <json>`（逐 case 调 `/api/v1/chat`，`user_id` 注入，断言关键词/脱敏/权限）

## 检验结果

**成绩单 kb_test_transcript.json：5/5 通过**
- transcript_001 总学分 → "148.5 / 必修102 / 选修46.5" ✅
- transcript_002 概率论成绩 → "概率论与数理统计 … 92分" ✅
- transcript_003 GPA → "3.57" ✅
- transcript_004 班级专业 → "信息管理与信息系统 / 2023级" ✅
- **privacy_001 脱敏 → 不泄露黄信烨/完整学号，学号显示 3123****52** ✅

**手册 kb_test_handbook.json：5/5 通过（含用户指定三问）**
- 休学期间待遇 → "学校保留其学籍，但不享受在校学习学生待遇"（来源：手册休学与复学部分）✅
- 集会游行示威 → "按法律程序和有关规定获得批准；未获批准依法劝阻或制止"（来源：校园秩序与课外活动部分）✅
- 入伍保留学籍 → "保留其学籍至退役后 2 年，服役时间不计入修业年限"（来源：第二十六条）✅
- 转专业 → "公开公平公正 + 兴趣导向"（来源：第四十二条）✅
- 注册手续 → "请假手续 + 暂缓注册手续"（来源：第九条）✅

**权限与隐私验证**：
- 成绩单仅在 `user_id=3123003252` 时检索到本人分区
- 隐私 case：回答主动说明"隐私脱敏"，不输出姓名/完整学号

## 经验与后续

- **真实向量显著提升检索**：占位向量下同义改写召回不准，真实 `text-embedding-v4` 下 10 个 case 全部命中正确分区，响应 3-13s。
- **断言用 OR 语义**：agent 措辞灵活（如"退役后 2 年"含空格），`expected_keywords` 用"任一命中"比"全命中"更稳；`expected_redact` 保持"必须都不出现"。
- 集会游行示威条款：手册含"按法律程序获得批准"等原则性表述，可回答但无专门申报流程细节——如实反映知识覆盖边界。
- 后续：可将 JSON 扩展为离线评测集（上下文召回率/忠诚度指标数据源）。
