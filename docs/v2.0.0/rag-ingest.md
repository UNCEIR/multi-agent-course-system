# RAG 摄入策略详解（三个 ingest 全链路）

> 本文档逐点说明三个数据摄入管道的**策略原理与落地细节**：
> 1. 公选课数据集 `ingest_course_dataset.py`
> 2. 学生手册 `ingest_student_handbook.py`（PDF 1）
> 3. 个人成绩单 `ingest_transcript_desensitized.py`（PDF 2）
>
> 适用于离线首次摄入与重复摄入（均为幂等）。所有脚本从 `python/` 目录执行，
> 依赖 `.env`（`MYSQL_PORT=3307` 等）与运行中的 Docker 依赖。

---

## 0. 通用基座（三个管道共用的能力）

### 0.1 解析：`tools/documents/parser.py` 的 `parse_document`

- **主解析 pypdf**：逐页 `page.extract_text()`，拼接到全文。
- **pymupdf 兜底**：pypdf 抽出的文本为空时，改用 `fitz` 抽取 `text` 模式，并对每页 `page.find_tables()` 做表格抽取，表格以 `cell1 | cell2` 管道符拼接进正文——解决手册/成绩单的表格版式。
- **NFKC 归一化**：`unicodedata.normalize("NFKC", text)` 修复 PDF 抽取的 Kangxi 变体字（如 `⼴→广`、`⻩→黄`）。

### 0.2 分块：`tools/documents/chunker.py` 的 `chunk_document`

默认参数 `chunk_size=800`、`chunk_overlap=120`、`strategy="recursive"`（手册/成绩单均用 recursive；课程数据不用它，见 §1）。

**recursive 策略三步：**

1. **按标题切"章节块"**（`_split_by_headings`）：
   - 标题正则 `_HEADING_RE` 只匹配真实标题行：`第X章/节/条/款/部分` 或 `一、/二、` 编号标题。
   - 标题 + 同行正文（如 `第一条 学生应当…`）→ 标题作为前缀、同行正文入块；纯标题行则作为下一块的 heading。
   - **目录行过滤** `_is_toc_line`：含 3+ 连续点号（`....`）的引导行、纯页码/罗马页码行不会成为标题。
2. **合并小块**（`_merge_small_blocks`）：相邻且 body 很短的块合并到接近 `chunk_size`，保留标题前缀，避免碎片化；超长块独立保留。
3. **递归切分超长块**（`_recursive_cut`）：按中文感知分隔符 `["\n\n", "\n", "。", "；", "，", ""]` 依次尝试，优先在句子边界断句；组内超 `chunk_size*1.5` 再递归；相邻块补充 `chunk_overlap`（取上一块尾部 `chunk_overlap` 字符拼到下一块头），防止边界语义丢失。

### 0.3 向量化：`ai/embedding_client.py` 的 `build_embedding_client`

- 按 `EMBEDDING_PROVIDER` 分派：
  - `openai`（当前 `.env` 值）→ `OpenAIEmbeddingClient`，底层 `langchain_openai.OpenAIEmbeddings`，`task_name` 决定 LangSmith trace 名（`documents_upload` / `backfill` / `query_knowledge`）。
  - `local` → `LocalDeterministicEmbeddingClient`（SHA-256 种子伪随机 + L2 归一化，零额度冒烟用，**检索无真实语义**）。
  - `dashscope_multimodal` → DashScope 原生 `/api/v1/services/embeddings/...`，按 batch 提交并校验维度。
- 维度一致性：`EMBEDDING_DIMENSION`（`.env`=1024）必须等于 Milvus collection 的 `milvus_dimension`，否则 upsert 报错。

### 0.4 幂等保证（增量更新去旧）

- Milvus：`DocumentVectorRepository.delete_by_dataset(dataset_id)` / 课程按 `course_id` 主键 `upsert` 覆盖。
- MySQL：`DocumentRepository.replace_chunks` 先 `DELETE WHERE dataset_id` 再批量插入；课程 `CourseRepository.replace_course_chunks` 先删该 `course_id` 再插入。
- 因此重复摄入不会残留旧版本 chunk。

### 0.5 双写结构

| 数据 | MySQL | Milvus |
|---|---|---|
| 课程 | `course_records`（结构化行）+ `course_chunks`（4 类 chunk 文本/元数据） | `course_chunks_real`（chunk 向量） |
| 手册 | `document_records`（dataset 元数据）+ `document_chunks`（正文/来源） | `document_chunks`（`user_id=public`） |
| 成绩单 | `document_records` + `document_chunks`（脱敏正文） | `document_chunks`（`user_id=<学号>`） |

> 检索时（`query_knowledge`）：Milvus 只回 `chunk_id/来源/距离`，正文从 MySQL `document_chunks` 按 `chunk_id` 取回，避免把大段 content 塞进向量库。

---

## 1. 公选课数据集：`python scripts/ingest_course_dataset.py --limit 250`

### 1.1 数据源

- CSV 路径（脚本默认值，`ingest_course_dataset.py:17`）：`course_dataset_tools/output/course.csv`。
- **现状**：`output/` 下当前数据源即 `course.csv`（`public_elective_courses.csv` 为重命名前的名字，字段一致）。
- 读取：`csv.DictReader`，`encoding="utf-8-sig"`（兼容 BOM），`--limit 250` 表示只取前 250 行。

### 1.2 逐行处理流程（每门课）

对每一行 row：

1. **写 MySQL 结构化行**：`course_repo.upsert_course(row)`（`course_repo.py:18`）
   - `INSERT ... ON DUPLICATE KEY UPDATE` 按 `course_id` 幂等覆盖。
   - 落库列：`course_id, course_name, teacher, credits, course_type, course_category, domain, campus, time_slot, capacity, current_enrolled, popularity_level, has_exam, group_work_required, tags, raw_json`。
   - `raw_json` 存整行原始数据；`has_exam/group_work_required` 用 `_parse_binary_flag` 把 `1/是/有/true` → `1`。
2. **构造 4 类 chunk**（`_build_chunks`，`ingest_course_dataset.py:92`）——按字段语义切分，避免整行 CSV 直接 embedding 导致语义混杂：

   | chunk_type | 字段 | 用途 |
   |---|---|---|
   | `basic` | 课程名称/教师/学分/类型/分类/方向 | 基础事实召回 |
   | `schedule_capacity` | 校区/上课时间/地点/限选/已选/比例/热度/抢课建议 | 时间、容量、热度筛选 |
   | `learning_profile` | 简介/考核方式/难度/作业量/给分友好度/是否考试/是否小组作业 | 学习体验偏好 |
   | `audience_tags` | 适合人群/标签/历年选课比例 | 目标人群匹配 |

   - `chunk_id = "{course_id}:{index}:{chunk_type}"`（如 `GXK2026001:0:basic`），保证每课 4 个 chunk 全局唯一。
   - `content` 用 `_render_chunk` 渲染为 `中文标签：值` 多行文本（`_display_value` 把 has_exam 等转成 `有/无`）。
   - `metadata_json` 存 `course_name/teacher/domain/course_category/tags` 供展示。
3. **写 MySQL 课程 chunk 元数据**：`course_repo.replace_course_chunks(course_id, chunks)`（先删后插，幂等）。
4. **写 Milvus 向量**：`vector_repo.upsert_chunks(chunks)`（`course_vector_repo.py:56`）
   - 取 4 个 chunk 的 content 一次批量 embed（`task_name=LLMTaskName.BACKFILL`），写入 `course_chunks_real`（schema：`chunk_id/course_id/chunk_type/embedding`，1024 维，COSINE + AUTOINDEX），最后 `flush()`。

### 1.3 规模与结果

- 250 门课 → MySQL `course_records` 250 行 + `course_chunks` 1000 行 + Milvus 1000 实体。
- 脚本结尾打印 `{"courses": 250, "chunks": 1000, "status": "ok"}`。
- **注意**：若中途被打断（如 embedding 超时），重跑即可——`upsert`/`replace` 幂等，最终行数不翻倍。
  （实测曾出现 Milvus `num_entities` 略大于 1000：Milvus 的 upsert 是逻辑覆盖，`num_entities` 可能把已被覆盖的旧主键也计入，实际可用数据以 MySQL `course_chunks=1000` 为准。）

### 1.4 消费方

- 在线召回：`CourseRecallAgent` 用 `query_embedding` 对 `course_chunks_real` 语义搜索 + MySQL 关键词/硬约束过滤；Redis 只缓存候选 `course_id` 列表，事实仍回 MySQL。

---

## 2. 学生手册：`python scripts/ingest_student_handbook.py`

> PDF 1 = `广东工业大学2025年学生手册.pdf`（仓库根目录，脚本默认路径）。

### 2.1 管道顺序

```
PDF → parse_document(pypdf/pymupdf, NFKC) → _strip_toc(去目录) → chunk_document(recursive) → embed → Milvus(user_id=public) + MySQL 元数据
```

### 2.2 关键策略点

1. **去目录**（`_strip_toc`，`ingest_student_handbook.py:28`）
   - 手册前 ~8 页是目录（点号引导行）。正文从 `高等学校学生行为准则` / `第一章  总` / `总  则` 等标记开始。
   - 关键：目录里也含这些字样但后跟 `....` 引导符；所以命中位置后 20 字符内若出现连续 `...` 就判定为目录行，继续向后找，直到命中"标记后无点号"的正文位置。
2. **分块**：recursive（§0.2），标题优先 + 中文分隔符 + 120 字符 overlap。
3. **dataset_id 确定性生成**：`handbook_2025_` + `sha256(pdf_path)[:8]`（当前 = `handbook_2025_acff6de8`）——同一路径重跑得到同一 id，天然幂等。
4. **先清旧再写**：`vector_repo.delete_by_dataset(dataset_id)` 删 Milvus 旧版；MySQL `doc_repo.create_dataset(...)`（`ON DUPLICATE KEY UPDATE`）+ `replace_chunks`（先删后插）。
5. **分区归属**：所有 chunk `user_id = PUBLIC_USER`（`public` 分区），公开知识，所有用户可检。
6. **元数据**：`chunk_type="generic_fixed"`、`page_number=0`（手册分块不追踪页号，靠 section/heading 上下文）、`source_doc_name=广东工业大学2025年学生手册.pdf`。
   - `query_knowledge` 回答时引用 `[来源: 学生手册 第X页]`——手册场景 page_number 为 0，引用退化为文档名 + 章节内容，属已知边界。
7. **embedding**：`task_name=LLMTaskName.DOCUMENTS_UPLOAD`，Milvus `document_chunks` collection（10 字段 schema，`user_id` 为 partition key）。

### 2.3 规模与结果

- 全量 = **221 chunks**（`total_parsed=221`，当前实测 `chunks=221`）。
- 冒烟：`--limit 30` 只摄入前 30 个 chunk；`--embedding local` 用零额度占位向量验证管道（检索无真实语义）。

---

## 3. 个人成绩单：`python scripts/ingest_transcript_desensitized.py --user-id 3123003252 --name 黄信烨`

> PDF 2 = `本科生中文成绩单(1860658).pdf`（仓库根目录，脚本默认路径）。

### 3.1 管道顺序

```
PDF → parse_document(NFKC) → PII 审计(build_pii_report) → desensitize_transcript(脱敏) → chunk_document(recursive) → embed → Milvus(user_id=学号) + MySQL 元数据
```

### 3.2 脱敏策略（`tools/documents/desensitizer.py`）——本管道核心

`desensitize_transcript(text, student_name, keep_grades=True)` 依次执行：

| 步骤 | 规则 | 示例 |
|---|---|---|
| NFKC 归一化 | `unicodedata.normalize("NFKC")` | 变体字修复 |
| Kangxi 部首映射 | `_fix_supplement_radicals`：CJK 补充部首 `U+2E80–2EFF` 手动映射（`⻩→黄`、`⻓→长` 等 16 个）——NFKC 不映射这些，不转则姓名命中不了脱敏规则 | `⻩信烨→黄信烨` |
| 姓名替换 | `replace_name`：`text.replace(student_name, "[姓名]")`，依赖调用方传 `--name` | 黄信烨 → `[姓名]` |
| 学号掩码 | `mask_student_id`：`\b\d{9,12}\b`，保留前 4 后 2 | `3123003252 → 3123****52` |
| 身份证掩码 | `mask_id_card`：18 位校验位正则，保留前 6 后 4 | `4401... → 4401********1234` |
| 手机掩码 | `mask_mobile`：`1[3-9]\d{9}`，保留前 3 后 4 | `138... → 138****1234` |
| 班级→年级 | `generalize_class`：`([中文]{2,12})(\d{2})\((\d+)\)` | `信息管理与信息系统23(3) → 2023级` |
| 日期→年份 | `generalize_date`：`(\d{4})[-/年]...` | `2026-07-28 → 2026年` |

- **`keep_grades=True`（默认）**：课程名、学分、成绩精确值**保留**——它们在用户私有分区内，用于回答"某科考了多少分/总学分多少"。
- **PII 审计**：`build_pii_report` 返回 `{student_id, id_card, mobile}` 计数（学号计数先剔手机号，避免 11 位手机被误计），脚本启动时打印审计行。

### 3.3 归属与隔离

- 所有 chunk `user_id = <user-id>`（当前 `3123003252`），Milvus `document_chunks` 以 `user_id` 为 partition key。
- 检索时 `query_knowledge` 只查 `["public", 当前用户 id]`，其他用户无法命中该分区（强过滤，非软偏好）。
- `dataset_id = "transcript_" + sha256(f"{user_id}:{pdf名}")[:8]`（当前 = `transcript_6bc5abed`），同一用户同一文件幂等。

### 3.4 分块与入库

- recursive 分块（§0.2）→ 本成绩单实测 **3 chunks**。
- 先 `delete_by_dataset` 清旧 → embed（`task_name=DOCUMENTS_UPLOAD`）→ upsert Milvus + MySQL `create_dataset(name="transcript_3123003252")` + `replace_chunks`。
- 无 `--limit` 参数（全量）；`--embedding local` 可冒烟。

---

## 4. 执行与验证记录（本次实测）

容器 `mult-agent-university-system-*` 全新空卷，三管道依次执行结果：

| 管道 | 命令 | MySQL | Milvus |
|---|---|---|---|
| 课程 | `python scripts/ingest_course_dataset.py --limit 250` | `course_records=250`、`course_chunks=1000` | `course_chunks_real`=1000 有效实体 |
| 手册 | `python scripts/ingest_student_handbook.py` | `document_records` +2、`document_chunks` +221 | `document_chunks`=221（public） |
| 成绩单 | `python scripts/ingest_transcript_desensitized.py --user-id 3123003252 --name 黄信烨` | `document_chunks` +3 | `document_chunks`=224（3 条 user_id=3123003252） |

- `PII audit (raw): {'student_id': 1, 'id_card': 0, 'mobile': 0}`（学号 1 处，掩码后 `3123****52`）。
- 端到端验证：`python scripts/run_kb_test.py scripts/kb_test_transcript.json` 与 `scripts/kb_test_handbook.json`（需 API 运行中）。

## 5. 常见问题

- **embedding 维度报错**：`EMBEDDING_DIMENSION` 与 Milvus collection 维度（当前 1024）必须一致。
- **`--embedding local` 结果不准**：占位向量无语义，只用于管道冒烟，正式数据必须用 `openai`/`dashscope_multimodal`。
- **重跑后 Milvus 计数偏大**：`num_entities` 可能计入已覆盖主键，以 MySQL 行数为准。
- **证书/SAN 报错**：`HTTPX_VERIFY_SSL=false` 写入 `.env` 后重建容器。
- **宿主 MySQL 端口**：本机 `MYSQL_PORT=3307`（Docker 映射），容器内为 3306。
