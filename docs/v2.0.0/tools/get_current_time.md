# get_current_time

**状态**: `implemented`
**Phase**: 1
**类别**: `system/*`

## 功能描述

获取当前日期和时间，用于 agent 记录操作时间、上下文感知等场景。

## 输入参数

无参数。

## 输出

当前日期时间字符串（格式：`YYYY-MM-DD HH:MM:SS`）。

## 失败兜底

- 纯本地调用，不依赖外部服务，无失败场景