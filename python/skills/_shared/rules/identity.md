# Shared Rules: identity（身份注入）

适用范围：所有涉及用户身份的 skill。

## 规则
1. 当前用户 `user_id` 已由系统自动注入（`agent.main.context`），**不得**向用户索要学号，**不得**在工具参数里猜测或编造 user_id。
2. 涉及个人数据（成绩单、评价、推荐）的工具，user_id 一律从上下文读取。
3. 匿名用户（user_id 为空）不触发个人数据链路。
