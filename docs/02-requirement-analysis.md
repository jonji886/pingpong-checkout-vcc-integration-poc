# Requirement Analysis

P0 的验收重点是最终一致性和资金安全：可信 Provider Observation 统一经过状态机；Credits 只能在 SUCCESS 后通过唯一 Ledger 入账；Webhook 可重复、乱序、延迟；未知结果查单而不是新建支付。P1 当前实现为 VCC Workflow Assistant：支持 deterministic parser 和可选 LLM 自然语言结构化解析，但预算、RBAC、审批、幂等和审计始终由后端确定性校验。
