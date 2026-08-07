"""
v2 Skills 技能目录 — SKILL.md 文件目录

当前状态：Phase 1 已实装两个技能，其余 Phase 2/3 技能骨架已就位。

什么是 Skills（deepagents SkillsMiddleware）：
  Skills 是 deepagents 内置的「渐进式披露」技能加载机制，遵循 Agent Skills Specification
  （https://agentskills.io/specification）。每个技能是一个子目录，内含 SKILL.md 文件：

    skills/
    ├── recommend-courses/       # 推荐课程技能（Phase 1）
    ├── document-ingestion/      # 文档摄入技能（Phase 1）
    ├── report-generation/       # 成绩单报告技能（Phase 2）
    ├── evaluation-writing/      # 评价寄语技能（Phase 2）
    ├── knowledge-query/         # 知识库问答技能（Phase 3）
    ├── web-search/              # 网页搜索技能（Phase 3）
    ├── deep-thinking/           # 深度思考技能（Phase 3）
    ├── writing/                 # 论文写作技能（Phase 3）
    └── ppt-generation/          # PPT 生成技能（Phase 3）

  create_deep_agent(skills=["/skills/"]) 时，SkillsMiddleware 自动：
    1. 扫描 skills/ 下所有含 SKILL.md 的子目录
    2. 解析 YAML frontmatter（name, description, allowed_tools）
    3. 注入到 system prompt（渐进式披露：先看名称+描述，需要时 read_file 读全文）
    4. Agent 识别用户意图 → 匹配技能 → read_file 读 SKILL.md → 按步骤执行

重要区分：
  - tools/（Python @tool 代码）: 原子能力，ToolRegistry 注册，供 Agent 直接调用
  - skills/（SKILL.md 文档）: 技能说明，SkillsMiddleware 注入 system prompt，供 Agent 阅读
  - ToolRegistry/CircuitBreaker/MCPClient 放 tools/ 下，不是 skills/

技能概览：
  ┌─────────────────────┬──────────┬──────────────────────────────────────┐
  │ 技能名称             │ Phase    │ allowed_tools                       │
  ├─────────────────────┼──────────┼──────────────────────────────────────┤
  │ recommend-courses   │ 1 (实装) │ recommend_courses                    │
  │ document-ingestion  │ 1 (实装) │ parse_document, chunk_document       │
  │ report-generation   │ 2 (骨架) │ compute_weighted_grade               │
  │ evaluation-writing  │ 2 (骨架) │ compute_weighted_grade               │
  │ knowledge-query     │ 3 (骨架) │ （无，检索知识库）                    │
  │ web-search          │ 3 (骨架) │ web_search                           │
  │ deep-thinking       │ 3 (骨架) │ （无，纯推理）                        │
  │ writing             │ 3 (骨架) │ writing_assistant, web_search        │
  │ ppt-generation      │ 3 (骨架) │ web_search                           │
  └─────────────────────┴──────────┴──────────────────────────────────────┘
"""