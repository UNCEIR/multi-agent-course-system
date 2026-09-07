---
name: deep-thinking
description: 对复杂问题进行深度分析和独立思考，不依赖外部工具，仅凭 LLM 推理能力进行系统性分析。当用户需要复杂问题分析、多因素权衡、方案构思时使用。 何时不用：需要实时数据或外部事实时请用 web-search / knowledge-query，不要纯推理编造。
allowed_tools: []
---

## Description
独立深度思考：复杂问题系统性分析（拆解→多视角→权衡→结论），不依赖外部工具。

## Trigger
用户提出复杂问题、需要多约束权衡、方案构思时激活。

## Architecture（按序加载）
1. Commands（执行流程）：
   - [Load Command: think-through](./commands/think-through.md)
