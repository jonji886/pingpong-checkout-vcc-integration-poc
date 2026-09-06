# Payment State Machine

`CREATED → PROCESSING → SUCCEEDED | FAILED | CANCELLED | REVIEW_REQUIRED`。Provider 状态映射：PENDING、SUCCESS、FAIL、CLOSE、AUTH_SUCCESS。终态单调不回退；AUTH_SUCCESS 不发 Credits。Create Response、验签 Webhook、Query/Reconciliation 共享同一 `PaymentService.apply_observation`。

退款是独立聚合：`CREATED → PROCESSING → SUCCEEDED | FAILED`，余额不足进入 `MANUAL_REVIEW`。Payment 成功事实不会被退款覆盖，UI 的 REFUNDED 由成功 RefundOrder 派生。

