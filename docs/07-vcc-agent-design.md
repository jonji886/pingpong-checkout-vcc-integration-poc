# VCC Agent Design

Agent 只负责从自然语言生成结构化 vendor/amount/currency/purpose/period，随后调用 Budget Tool 和 Approval Service。月度云预算为 50,000 USD，已用 10,000；超过 1,000 USD 必须人工审批。只有 `APPROVED` 申请才能执行 Create VCC Tool；Tool 在后端重做状态、RBAC、幂等检查并写 Audit。LLM 永不接触 Provider Secret。

不超过 1,000 USD 的申请可由确定性策略标为 `AUTO_APPROVED`，不代表 Agent 自行授权。
