# react_vs_pipeline A/B 实验落地笔记

## 实验目的
对比 ReAct 流式推荐 (`/api/v1/recommend/react/stream`) 与 Pipeline 流式推荐 (`/api/v1/recommend/stream`) 的:
- 响应时间 (total_latency_ms)
- 返回课程数 (course_count)
- 选课提醒数 (warning_count)
- 成功率 (success/failure)

## 后端改动: python/orchestrator/supervisor.py
- `stream_recommend()` 的 done 处调用 `self.ab_engine.record_outcome + record_metric` (group="pipeline")
- `stream_recommend()` 的 error 处调用 `self.ab_engine.record_outcome` (success=False)
- `react_stream_recommend()` 的 done 处同样 (group="react")
- `react_stream_recommend()` 的 error 处同样 (success=False)

## 前端改动: frontend/src/pages/MonitorPage.tsx
- A/B 实验展开区: react_vs_pipeline 实验的 stats 数据替换为格式化指标卡片 (两列对比: Pipeline vs React, 显示 mean/min/max)
- 其他实验保持原样

## 不改动
- 端点路径不变
- ab_test.py 实验定义不变
- 前端对比测试卡片不动
- 非流式 recommend() 不参与
