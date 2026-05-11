# 学校公选课 Multi-Agent 推荐系统

> 面向教务系统在校生的 AI Agent 项目：学生用自然语言描述选课偏好，系统自动理解需求、召回课程、重排课程、评估选课可行性，并给出可解释推荐理由。

## 项目定位

这个项目现在定位为学校公选课推荐系统。用户是教务系统中的在校学生；被推荐对象是公共选修课。

## 文档导航

- 当前主线（公选课）
  - [README](README.md)
  - [面试讲解文档](docs/interview-guide.md)
  - [课程改造设计](docs/plans/2026-05-11-course-agent-redesign.md)
  - [课程数据集工具](course_dataset_tools/README.md)
- Legacy 对照（历史电商叙事）
  - [系统架构（Legacy）](docs/architecture.md)
  - [项目规划（Legacy）](docs/project-plan.md)
  - [代码讲解（Legacy）](docs/code-walkthrough.md)
  - [简历模板（Legacy）](docs/resume-template.md)

学生可以输入类似下面的 prompt：

```text
我想选一门不考试、作业少、给分友好的公选课，最好在东校区，周三晚上不要有课，
我对电影、心理学和艺术比较感兴趣，不想做小组作业。
```

系统会输出：

- 推荐课程列表
- 每门课的匹配理由
- 爆满、容量紧张、时间冲突、限制条件等选课风险
- 各 Agent 的执行结果，便于调试和面试讲解

## 为什么适合做 Agent 项目

公选课推荐不是简单关键词搜索。学生的需求通常混合了兴趣、时间、校区、考核方式、难度、作业量、绩点诉求和抢课风险。

单个 Agent 容易把所有判断塞在一个 prompt 里，导致上下文臃肿、可解释性差、失败后不好降级。本项目拆成多个专业 Agent：

| Agent | 职责 | 输入 | 输出 |
|---|---|---|---|
| 学生画像 Agent | 从自然语言 prompt 抽取选课偏好和硬约束 | prompt、context | `StudentProfile` |
| 课程召回 Agent | MySQL 结构化筛选 + Milvus 语义召回 | 学生需求、课程向量库 | 候选课程 |
| 课程重排 Agent | 综合兴趣匹配、时间、考核、难度、容量进行排序 | 学生画像、候选课程 | TopN 排序 |
| 选课可行性 Agent | 检查容量、爆满、时间冲突、年级/专业/先修限制 | 候选课程、学生上下文 | 可选课程与风险提醒 |
| 推荐理由 Agent | 生成面向学生的解释 | 最终课程、风险提醒 | 推荐理由 |

## 系统架构

```text
学生 prompt
  |
  v
Supervisor 编排器
  |
  +-- Phase 1 并行
  |     +-- 学生画像 Agent：抽取兴趣、时间、校区、考核、难度、作业量偏好
  |     +-- 课程召回 Agent：MySQL 筛选 + Milvus 课程 chunk 语义检索
  |
  +-- Phase 2 并行
  |     +-- 课程重排 Agent：LLM 精排课程
  |     +-- 选课可行性 Agent：容量、爆满、冲突、限制检查
  |
  +-- Phase 3 串行
        +-- 推荐理由 Agent：生成推荐理由和选课建议
  |
  v
课程列表 + 推荐理由 + 选课风险 + Agent 轨迹
```

核心代码：

- [python/orchestrator/supervisor.py](python/orchestrator/supervisor.py)
- [python/agents/student_profile_agent.py](python/agents/student_profile_agent.py)
- [python/agents/course_recall_agent.py](python/agents/course_recall_agent.py)
- [python/agents/course_rerank_agent.py](python/agents/course_rerank_agent.py)
- [python/agents/course_feasibility_agent.py](python/agents/course_feasibility_agent.py)
- [python/agents/recommendation_reason_agent.py](python/agents/recommendation_reason_agent.py)

## 数据集如何上传到向量库

已有数据集：

[course_dataset_tools/output/public_elective_courses.csv](course_dataset_tools/output/public_elective_courses.csv)

不要把 CSV 每一整行直接向量化。推荐使用“结构化主表 + 语义分块向量库”的方式：

| 层 | 存什么 | 作用 |
|---|---|---|
| MySQL `course_records` | 每门课完整结构化信息 | 回表展示、规则过滤、容量判断 |
| MySQL `course_chunks` | 每门课拆出来的文本块 | 保留 chunk 内容和元数据 |
| Milvus `course_chunks` / `course_chunks_real` | 每个 chunk 的 embedding | 根据学生 prompt 做语义召回 |

默认每门课拆成 4 个 chunk：

| chunk 类型 | 字段 |
|---|---|
| `basic` | 课程名、教师、学分、课程类型、课程分类、领域 |
| `schedule_capacity` | 校区、上课时间、地点、容量、已选人数、热度、抢课建议 |
| `learning_profile` | 简介、考核方式、难度、作业量、给分友好、考勤、考试、小组作业 |
| `audience_tags` | 年级限制、专业限制、先修要求、适合人群、标签、历年选课比例 |

这样用户说“不要考试、作业少、给分友好、周三晚上不行”时，系统能分别命中学习体验 chunk 和时间容量 chunk，再通过 `course_id` 回 MySQL 拿完整课程。

## 快速运行

### 1. 安装 Python 依赖

```bash
cd python
python -m pip install -r requirements.txt
```

### 2. 配置 LLM 和 Embedding

在 `python/.env` 中配置：

```env
ECOM_LLM_API_KEY=你的LLM Key
ECOM_LLM_BASE_URL=https://你的OpenAI兼容地址/v1
ECOM_LLM_MODEL=你的模型

ECOM_EMBEDDING_PROVIDER=local
ECOM_EMBEDDING_DIMENSION=64
ECOM_MILVUS_DIMENSION=64
ECOM_COURSE_MILVUS_COLLECTION=course_chunks
```

如果使用真实 embedding，把 provider、base_url、api_key、model、dimension 改成对应服务即可。

### 3. 启动依赖服务

```bash
docker compose -f docker-compose.python.yml --profile python up -d --build
```

### 4. 导入课程 CSV 到 MySQL 和 Milvus

```bash
cd python
python scripts/ingest_course_dataset.py --limit 20
python scripts/ingest_course_dataset.py
```

导入脚本会执行：

1. 读取 `public_elective_courses.csv`
2. 写入 `course_records`
3. 生成 `basic`、`schedule_capacity`、`learning_profile`、`audience_tags` 四类 chunk
4. 写入 `course_chunks`
5. 生成 embedding 并写入 Milvus

### 5. 启动 API

```bash
cd python
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 6. 调用推荐接口

```bash
curl -X POST http://localhost:8000/api/v1/recommend ^
  -H "Content-Type: application/json" ^
  -d "{\"user_id\":\"S10001\",\"num_items\":5,\"prompt\":\"想选不考试、作业少、给分友好的艺术类公选课，东校区优先，周三晚上不要有课\",\"context\":{\"avoid_time_slots\":[\"周三第9-10节\"],\"campus\":[\"东校区\"]}}"
```

响应示例：

```json
{
  "request_id": "7d6d...",
  "user_id": "S10001",
  "courses": [
    {
      "course_id": "GXK2026003",
      "course_name": "风景地貌学",
      "teacher": "杨雪强",
      "domain": "自然环境",
      "campus": "东校区",
      "time_slot": "周四第7-8节",
      "has_exam": "否",
      "workload": "中",
      "grade_friendly": "中"
    }
  ],
  "recommendation_reasons": [
    {
      "course_id": "GXK2026003",
      "reason": "课程位于东校区且不考试，内容偏自然环境拓展，适合希望用公选课拓宽知识面的学生；但当前热度较高，建议提前抢课。"
    }
  ],
  "selection_warnings": [
    {
      "course_id": "GXK2026003",
      "level": "high",
      "type": "capacity_full",
      "message": "当前已选人数达到或超过容量，建议作为冲刺志愿并准备替代课程。"
    }
  ],
  "experiment_group": "control",
  "total_latency_ms": 1530.2
}
```

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/recommend` | Supervisor 主链路课程推荐 |
| `POST` | `/api/v1/recommend/graph` | LangGraph 状态图版本 |
| `GET` | `/api/v1/experiments` | 查看 A/B 实验状态 |
| `GET` | `/api/v1/metrics` | 查看 Agent 调用指标 |
| `GET` | `/health` | 检查 MySQL、Redis、Milvus |

## 常见问题与排障

- MySQL 或 Milvus 未就绪
  - 先执行 `docker compose -f docker-compose.python.yml --profile python up -d --build`
  - 再检查 `GET /health`，确保依赖服务可达
- embedding 维度不一致
  - 保持 `ECOM_EMBEDDING_DIMENSION` 与 `ECOM_MILVUS_DIMENSION` 一致
  - 如果已写入旧维度数据，建议清空对应 collection 后重新导入
- 课程 collection 配置错误
  - 检查 `ECOM_COURSE_MILVUS_COLLECTION` 是否与导入脚本写入目标一致
  - 需要切换 collection 时，先确认 `scripts/ingest_course_dataset.py` 的运行参数与配置
- Windows 和 Linux curl 差异
  - README 示例使用 Windows `^` 换行风格
  - Linux/macOS 请改为 `\\` 换行，或单行执行请求命令

## 项目结构

```text
multi-agent-ecommerce-system/
├── README.md
├── course_dataset_tools/
│   └── output/public_elective_courses.csv
├── docs/
│   ├── interview-guide.md
│   ├── architecture.md
│   ├── project-plan.md
│   ├── code-walkthrough.md
│   ├── resume-template.md
│   └── plans/2026-05-11-course-agent-redesign.md
├── python/
│   ├── main.py
│   ├── models/schemas.py
│   ├── orchestrator/
│   │   ├── supervisor.py
│   │   └── graph.py
│   ├── agents/
│   │   ├── student_profile_agent.py
│   │   ├── course_recall_agent.py
│   │   ├── course_rerank_agent.py
│   │   ├── course_feasibility_agent.py
│   │   └── recommendation_reason_agent.py
│   ├── repositories/
│   │   ├── course_repository.py
│   │   └── course_vector_repository.py
│   └── scripts/ingest_course_dataset.py
└── docker-compose.python.yml
```

## 面试亮点

- **Multi-Agent 拆分合理**：学生画像、课程召回、课程排序、可行性判断、推荐解释各司其职。
- **RAG 和结构化过滤结合**：Milvus 负责语义召回，MySQL 负责精确字段和回表展示。
- **Supervisor 并行编排**：画像和召回并行，重排和可行性检查并行，降低端到端延迟。
- **强可解释性**：输出推荐理由和风险提醒，适合教务场景而不是黑盒推荐。
- **真实数据集闭环**：已有公选课 CSV，可导入 MySQL 和 Milvus 跑通完整链路。

## 简历写法

```text
学校公选课 Multi-Agent 推荐系统 | 个人项目 | 2026.05
• 设计面向教务系统的公选课推荐 Agent 项目，支持学生通过自然语言 prompt 描述选课偏好
• 设计 Supervisor 多 Agent 编排链路，包含学生画像、课程召回、课程重排、选课可行性和推荐理由 5 个 Agent
• 基于 MySQL + Milvus 构建课程 RAG 数据层，将公选课 CSV 拆分为 basic、schedule_capacity、learning_profile、audience_tags 四类 chunk
• 使用 LLM 对学生兴趣、时间约束、考核偏好、难度和作业量诉求进行结构化抽取，并结合课程字段进行可解释重排
• 输出课程推荐理由、容量/爆满/时间冲突/限制条件风险提醒，提升推荐结果在教务选课场景下的可信度

技术栈：FastAPI · LangGraph · Multi-Agent · Milvus · MySQL · Redis · Docker · OpenAI-Compatible LLM
```

## 当前说明

仓库名仍保留历史名称 `multi-agent-ecommerce-system`，但 Python 主链路、README 和面试文档已经改为学校公选课推荐主题。历史 Agent 文件仅作对照，不再作为主推荐 API 的业务链路。
