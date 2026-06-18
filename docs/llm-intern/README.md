# LLM Intern 项目包装

本目录按照 llm-intern 技能方法论，对「学校公选课 Multi-Agent 推荐系统」项目进行系统化包装。**不修改任何源代码**，仅基于已有代码和验证结果做文档输出。

## 核心原则

```text
不虚构。先诊断，后包装。
```

- 所有声明必须有代码证据或测试验证支撑
- 区分「可以写」「谨慎写」「补证据后写」「不能写」「无法判断」
- 不用"主导"除非真的主导，不用"上线"除非真的上线
- 真实未知数据标注"待补充"

## 文档分工

| 文档 | 作用 | 何时用 |
| --- | --- | --- |
| `01_truth_boundary.md` | 系统化真值边界分类——逐条声明标注可信度 | 写简历/口播前检查每句话 |
| `02_evidence_contract.md` | 证据契约——每条强声明→代码位置→测试验证→面试风险→安全措辞 | 被追问时找证据 |
| `03_fit_verdict.md` | 按 LLM 实习岗位类型评估项目匹配度（RAG/Agent/后端/推荐） | 投递不同方向时切换侧重点 |
| `04_upgrade_plan.md` | 证据升级计划——半天/1天/3天/1周 | 投递截止前快速补短板 |

## 与已有文档的关系

本目录**不替代** `docs/` 根目录下的已有文档，而是补充 llm-intern 方法论特有的结构化分析层：

| 已有文档 | 本目录补充 |
| --- | --- |
| `docs/resume-template.md`（含 可以写/不要写） | `01_truth_boundary.md` 逐条系统化分类，覆盖所有可声明点 |
| `docs/interview-question-bank.md`（含证据引用） | `02_evidence_contract.md` 正式证据契约格式，文件:行号级别 |
| `docs/interview-guide.md`（含按岗位切换侧重点） | `03_fit_verdict.md` JD 匹配度评估 + fit verdict |
| 无对应 | `04_upgrade_plan.md` 时间分级的证据补充计划 |

## 推荐使用路径

1. **写简历前**：先读 `01_truth_boundary.md`，确认每句话在哪个可信度等级
2. **准备口播前**：对照 `02_evidence_contract.md`，确保关键声明有代码证据
3. **投不同方向**：读 `03_fit_verdict.md`，切换项目描述的侧重点
4. **还剩几天**：读 `04_upgrade_plan.md`，挑能快速完成的升级项

## Fit Verdict 速览

| 岗位方向 | 匹配度 | 核心优势 | 最大短板 |
| --- | --- | --- | --- |
| AI Agent / LLM 应用 | **强匹配** | 多 Agent 协作、Pipeline+ReAct 双模式、硬约束锁死 | 无真实用户反馈闭环 |
| 后端工程 / AI 基础设施 | **中等匹配** | FastAPI+SSE、缓存设计、embedding 复用优化 | 无压测数据、无 CI/CD |
| 推荐系统 / RAG | **中等匹配** | MySQL+Milvus+Redis 三层、chunk 策略、评分职责分离 | 无 CTR/召回率等业务指标 |
| 大模型算法 / 训练 | **弱匹配** | Agent 编排经验可迁移 | 无模型训练/SFT/RLHF 经验 |

详见 `03_fit_verdict.md`。
