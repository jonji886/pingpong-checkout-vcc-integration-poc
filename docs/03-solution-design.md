# Solution Design

FastAPI → Application Service → Domain State Machine → `CheckoutProvider` / `IssuingProvider`。SQLite 是默认数据库，模型包含 PaymentOrder、RefundOrder、CreditLedger、CreditHold、ApiIdempotency、WebhookEvent、ProviderCallLog、AuditLog 和 VCCApplication。

Mock 与 Sandbox 遵守同一 Port 语义。Provider 调用在本地事务外；Webhook 在验签后以短事务写事件、状态和 Ledger。金额始终是 Decimal/Numeric。Sandbox 的账户级字段和签名不在未知时猜测，缺前置条件保持 Sandbox Pending。

