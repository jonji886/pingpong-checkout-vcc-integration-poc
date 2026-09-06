# Webhook Design

处理顺序：raw body 验签 → DTO/allowlist 解析 → 订单/金额/币种匹配 → 短 DB transaction → 状态机 → idempotent ledger → ACK。

PingPong 当前公开 Checkout V4 notification 页面没有稳定 `event_id`/`delivery_id` 字段，因此本地使用 `delivery_fingerprint`（canonical payload hash）作为重复投递防护值；它不是 Provider event ID。未来只有在官方账户契约明确提供唯一 ID 时，才填 `provider_event_id` 并按 `provider + provider_event_id` 去重。

Layer A 是 delivery/event 去重；Layer B 是 Payment State Machine + `CreditLedger` unique constraint 的业务效果幂等。重复或乱序通知不会让 `SUCCEEDED` 回退，也不会再次入账。未知订单、金额/币种不符和未知状态写 `REJECTED` 安全事件并安全确认；临时数据库错误应返回 5xx 以触发 Provider 重试。

原始 Body、签名、token、动作 URL 和 PII 不落库。Webhook Provider delivery 按 at-least-once/uncertain 处理；本地 ledger 只承诺数据库事务边界内的 idempotent business effect。
