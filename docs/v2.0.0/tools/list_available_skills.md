# list_available_skills

**状态**: `implemented`
**Phase**: 1
**类别**: `system/*`

## 功能描述

列出当前可用的所有技能（skills_metadata 中的 skill 名称与描述）。由 SkillsMiddleware 自动注入 skills_metadata 到 state，agent 可通过 state["skills_metadata"] 读取。

## 输入参数

无参数。

## 输出

返回提示文本，引导 agent 查看系统提示中的技能列表。

## 失败兜底

- 纯文本返回，不依赖外部服务，无失败场景