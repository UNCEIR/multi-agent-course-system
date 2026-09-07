# 8 条项目记忆 × 仓库证据逐条核查（2026-09-06 考古版）

> 用途：把 2026-09-06 会话开头的 8 条记忆逐条对齐仓库证据，回答"这个数怎么测出来的、出处在哪、能不能背"。
> 配套：docs/interview-star-stories-phase4.md（2026-09-02 核对版）是主叙述文档；本文只补证据行号与高危数字真相。
> 复核方法：所有路径/行号均为本日实测；json 报告在 python/eval/reports/，评测集在 python/eval_sets/。

## 0. 当前评测资产总览（实测）
- 评测集 9 个 jsonl，合计 78 case：
  chat_intent=24、evaluation_comment=12、evaluation_comment_live=6、kb_retrieval=10、report_math=10、report_math_live=2、image_generate=5、image_recognize=4、web_search=5。
- eval/reports/ 现存报告 json 23 份（按 set 计数：chat_intent 5 + evaluation_comment 3 + evaluation_comment_live 2 + kb_retrieval 4 + report_math 3 + report_math_live 2 + image_generate 1 + image_recognize 1 + web_search 2）。
- → "9 集 78 case / 23 份报告"可直接背（比"8 集 74 / 22"新且准）。

## 1. Chat 智能体
| 记忆断言 | 证据 | 结论 / 推荐口径 |
|---|---|---|
| 意图链路正确率 94% | 全仓无此数（git log -S"94%" 无结果；docs/README/eval 均无） | **高危，删或自证**。可背的替代：09-01 smoke 24/24=100%（chat_intent-2026-09-01.json，easy13/med8/hard3）；教师端真实链路 4/4（08-18 live） |
| 真实链路失败 case 1/5 → 4/4 | 属实：chat_intent-2026-08-17.json live total=5 passed=1 rate=0.2 → chat_intent-2026-08-18.json live total=4 passed=4 | 直接背；教训笔记 docs/v2.0.0/notes/2026-08-18-chat-intent-4-badcase-fix.md |
| 注册 29 个工具 | runtime.py:131 主注册列表 + :163 documents 2 个（≈27+2=29）；主 agent 白名单 specs.py 现 21 | 简历可写"注册 29 个"；被追问能说白名单 21 的口径差 |
| user_id 由 ContextVar 注入 | 属实（agent/main/context.py get_current_user_id；docs/v2.0.0/notes/2026-08-09-user-id-injection.md） | 可背 |

## 2. Recommend 智能体
| 记忆断言 | 证据 | 结论 / 推荐口径 |
|---|---|---|
| 语义缓存用 Redis zset | **查无**：recall_cache_repo.py 无 zadd/zrange；实际是 Redis **Set 桶**（smembers，~line 198）+ 每个 key 的 meta JSON（含 embedding）+ **Python 端 _cosine_similarity 线性扫描**（line 263+） | **高危，改口径**："Redis 候选桶 + 元数据 JSON + Python 余弦比较，阈值 >0.95 复用" |
| 余弦 >0.95 复用候选 | 属实（similarity_threshold 参数；0.95 阈值另有 0.94 误命中实证，见 phase4 可追问点 3） | 可背，但别说 zset |
| 硬约束 + ReAct/Pipeline 双模式 A/B | 属实（hard_constraint_filter.py；ab_test 一致性哈希；note 2026-08-09-recommend-default-pipeline-speedup.md） | 可背 |
| 提速效果 | 同 note 第 28-29 行：ReAct total_latency_ms=205957.6（205.9s）→ Pipeline 并行 60318.9（60.3s，**降 71%**） | **推荐 206s→60s 可背**（有实测出处） |

## 3. Report 智能体
| 记忆断言 | 证据 | 结论 |
|---|---|---|
| 37 份学生 PDF 全量正确 | 属实：note 2026-08-18-phase3-live-eval-fulfillment.md:51 "report_math_live 2/2 通过（37 学生 PDF 全成）"；报告 report_math_live-2026-08-18.json total=2 passed=2，p95≈910.8s/批（12~15min 相符） | 直接背；2 个 live case 是批量/结构断言（batch_id、failed=0、students 含 url） |
| Excel 解析→完整性校验→并发渲染→PDF→MinIO | 属实（tools/report/、test_report_parse_score_excels.py、test_report_merge_students.py、test_report_fill_html.py） | 可背 |

## 4. Evaluation 智能体（反幻觉）
| 记忆断言 | 证据 | 结论 / 推荐口径 |
|---|---|---|
| 幻觉 case 拦截率 100% | 部分证据：evaluation_comment_live 08-17 6/6（eval_live_01..06）；evaluation_comment.jsonl 12 case 含"幻觉数字/混合幻觉/幻觉演示-自算统计被拦/引用缺失拒绝"反例 | 100% 是"反例演示都拦下"层面；若背 100% 需自证统计口径。稳妥口径："反幻觉硬闸：输出数字必须可溯源，违规重试后规则兜底；真实链路 6/6、评测集含幻觉反例全部拦截" |
| 寄语真实链路通过率 98% | **查无**：全仓仅 git 历史 faf0fd8:README.md:574 出现"好评率 98%"（电商 demo 文案，与寄语无关） | **高危，删或自证**。替代：live 6/6=100%（08-17） |
| 工作流：确定性源→结构校验→指标归因→引用核验硬闸 | 属实（agent/evaluation、tools/evaluation） | 可背 |

## 5. RAG
| 记忆断言 | 证据 | 结论 |
|---|---|---|
| heading-aware 递归切分 | 属实（documents 摄入管线；note 2026-08-25-documents-pipeline-silent-failure.md 等） | 可背 |
| 手册公共 top_k=5、成绩单个人分区 top_k=3 | 属实（query_handbook/query_transcript 工具；kb_retrieval 评测集 10 case） | 可背 |
| 课程推荐按语义拆 4 类 chunk | 属实：ingest_course_dataset.py::_build_chunks 拆 basic/schedule_capacity/learning_profile/audience_tags，chunk_type+tags 入库，召回按 course_id 聚合 | 可说"4 类语义分块含 tags 元数据"；**别说"已按 chunk_type 硬过滤建标签"**（维度过滤未强落地） |

## 6. Memory 机制
| 记忆断言 | 证据 | 结论 |
|---|---|---|
| 压缩写后同步持久化 / 双模板续写 / 前缀检测规则兜底 | 属实（tests：test_memory_compaction/test_summarization_sync/test_main_agent_memory；note 2026-09-02-memory-async-dual-template-fix.md） | 可背 |
| Token 预算+模型上下文单点决策压缩时机 | 属实（SummarizationMiddleware trigger=("tokens", cw-13000)） | 可背 |

## 7. LangSmith + LLM-as-Judge
| 记忆断言 | 证据 | 结论 / 推荐口径 |
|---|---|---|
| 8 评测集 74 case / 22 报告 | 过时快照（image_recognize 落库前） | 改口 **9 集 78 case / 23 份报告**（见第 0 节实测） |
| 后端单测 446 | 历史口径（旧 README/docs）；2026-09-02 实测 not slow 收集 464/468 | 改口 **460+**；446 会被戳穿过时 |
| judge 三执行器 + NDCG/F1 + LangSmith 回写 | 属实（eval/judge.py、observability、test_eval_judge.py） | 可背（注意：kb_retrieval 报告含 ndcg/f1 字段；judge 默认不 full 跑省配额——被问要诚实） |

## 8. 流式 / SSE
| 记忆断言 | 证据 | 结论 / 推荐口径 |
|---|---|---|
| 端到端 p95 22.8s→14.5s | **22.8 查无**；最接近真相：08-17 live p95=**228132ms≈228.1s**（那次仅 1/5 通过，case api_latency_ms=227897.3）→ 08-18 修复后 4/4，**p50=14501.6ms≈14.5s、p95=25653.7ms≈25.7s** | **高危，别背 22.8→14.5**（把 228.1s 误读成 22.8、且 14.5 是 p50 不是 p95，还混了两个质量状态）。可选替代口径：① 推荐管线 206s→60s（有出处）；② chat 真实链路修复后 p50=14.5s/p95=25.7s（08-18）；③ SSE 断线续传不丢事件（功能断言） |
| 单调事件 ID + Last-Event-ID 续传；前端 500ms→1s→2s 退避；4 端点 done/error | 属实（services/sse_event_buffer.py、frontend/src/lib/sse.ts、tests/test_sse_event_buffer.py、test_stream_recommend.py） | 可背 |

## 高危数字速查（面试前必看）
1. **94%**：全仓无出处 → 删；用 24/24（smoke）或 4/4（真实链路）。
2. **Redis zset**：实现是 Set+JSON+Python 余弦 → 改口径。
3. **寄语通过率 98%**：无出处，疑似电商 demo "好评率 98%" 残留 → 删；用 live 6/6。
4. **22.8s→14.5s**：查无；疑似 228.1s(失败轮 p95) 误读 + p50=14.5s 拼接 → 别背；用 206s→60s 或 08-18 p50=14.5s/p95=25.7s。
5. **后端单测 446**：过时 → 460+。
6. **8 集 74 case / 22 报告**：过时 → 9 集 78 case / 23 份。

## 仍待用户自证（仓库查不到，别背）
- chat_intent 94% 若坚持用，需给出统计口径（几 case、是否真实链路、日期）。
- 幻觉拦截 100% / 寄语 98% 若坚持用，需给出评测统计口径。
- 端到端 p95 22.8s→14.5s 若坚持用，需给出端点、采样次数、冷/热缓存口径。
