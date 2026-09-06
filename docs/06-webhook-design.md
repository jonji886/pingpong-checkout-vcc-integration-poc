# Webhook Design

先验签，再解析 allowlist；`event_key` 使用 `checkout.payment:{transaction_id}:{status}` 或 refund 对应键，不依赖 delivery/message ID。未知订单、金额/币种不符和未知状态写 REJECTED 安全事件并返回确认体；临时数据库错误返回 5xx。数据库唯一约束和 Ledger 唯一键共同防止并发重复入账。原始 Body、签名、token、动作 URL 和 PII 不落库。

