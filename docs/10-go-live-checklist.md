# Go-live / Customer Acceptance Checklist

> 本项目没有真实 Go-live；下面是 FDE 接入与上线前验收清单，不是生产上线证明。所有 `[ ]` 都需要实际证据后才能勾选。

## Contract and Credentials

- [ ] 已确认 Checkout API version、site/region 和四个实际 endpoint。
- [ ] 已取得 Sandbox/Production 的 `accId`、`clientId`、salt/签名配置，并通过 Secret Manager 注入。
- [ ] 已确认商户 product permission、enabled payment methods、currency/country、payment method/device/goods 要求。
- [ ] 已确认 Hosted (`prePay`) 产品权限、customer action contract，以及是否另有 API-only (`unifiedPay`) 需求。
- [ ] 已完成官方 Authentication/Signing 样例验证；没有根据别的平台猜算法。

## Callback and Security

- [ ] `notificationUrl` 为公网可达 HTTPS 完整路径，未使用 localhost/intranet/query 参数。
- [ ] raw body 在内存中完成验签；验签失败不解析业务、不入账。
- [ ] 已验证 Payment/Refund notification 的 status、ID、金额和币种核对。
- [ ] 已确认是否有官方 event/delivery ID；没有则使用本地 `delivery_fingerprint` 并在文档中标明不是 Provider event ID。
- [ ] 日志/Audit/测试快照不含 Authorization、salt/private key、完整 token、PAN、CVV、PII 或 payment action URL。
- [ ] 已验证 Secret rotation、最小权限、RBAC 和 webhook endpoint 防护。

## Reliability and Money Safety

- [ ] Client Idempotency-Key 的 replay/conflict 行为已验收。
- [ ] Provider `merchantTransactionId + requestId` 语义已确认；timeout 不会生成第二笔 Payment。
- [ ] Create/Query/Refund/Refund Query 的 retry policy 已区分；429 读取 Retry-After，所有 retry 有上限。
- [ ] 已验证 timeout→Query recovery、5xx、429、丢 webhook、重复 webhook、乱序 webhook。
- [ ] Payment success 与 TOPUP ledger 在同一本地 transaction boundary，ledger unique constraint 可证明一次业务效果。
- [ ] RefundOrder + CreditHold 原子创建；成功 settle、失败 release、余额不足不调用 Provider。
- [ ] 已验证 PostgreSQL 目标环境的 locking/unique constraint；SQLite 限制不被当作生产并发证明。

## Observability and Operations

- [ ] 能从 `trace_id`、`local_payment_id`、`request_id`、`partner_transaction_id`、`transaction_id`、`refund_id` 定位完整链路。
- [ ] Provider call、Webhook、Audit 和 Reconciliation 查询有权限保护。
- [ ] 已配置 429、5xx、长时间 PROCESSING、ledger mismatch、signature failure 告警。
- [ ] 已准备 Query/Reconciliation、Refund stuck、重复支付和 callback 失败 runbook。
- [ ] 已明确人工升级渠道、Provider 支持所需去敏字段和 response time。

## Acceptance / Rollout

- [ ] 使用无真实资金的 Sandbox test card 完成 Create → Query/Webhook → Credits → Refund。
- [ ] 支付失败、CANCEL/CLOSED、AUTH_SUCCESS、退款 FAILED/PROCESSING 均有证据。
- [ ] payment method enablement、currency/country、金额小数位和风控限制已确认。
- [ ] 已完成回滚/feature flag/停止创建 Payment 的操作说明。
- [ ] 已完成 Sandbox acceptance sign-off 和 production cutover checklist。
- [ ] Production smoke test、告警、回滚和 Secret rotation owner 已明确。

当前仓库状态：Mock 已验证；公开 Contract fixture/adapter test 已验证；没有真实成功 Sandbox payment、VCC issuance 或 Go-live，因此 `SANDBOX_PENDING` 必须保留。
