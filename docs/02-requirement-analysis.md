# Requirement Analysis

P0 的验收重点是最终一致性和资金安全：可信 Provider Observation 统一经过状态机；Credits 只能在 SUCCESS 后通过唯一 Ledger 入账；Webhook 可重复、乱序、延迟；未知结果查单而不是新建支付。P1 的 VCC Agent 只做自然语言解析和编排，预算、RBAC、审批、幂等和审计由后端确定性校验。

