# Troubleshooting Guide

- Payment 长时间 PROCESSING：使用 Admin reconcile；timeout/429 保留原 request/transaction ID，不新建订单。
- Credits 未增加：检查验签、WebhookEvent、Provider status 和 Ledger 唯一键。
- 409：同一 actor/route/key 的 payload 已变化，必须使用新幂等键。
- 退款 MANUAL_REVIEW：可用 Credits 不足，系统不会调用 Provider 或产生负余额。
- Sandbox 启动失败：检查显式 `PINGPONG_MODE=sandbox`、凭证、base URL 和 HTTPS notify URL；不要把 Mock 结果当 Sandbox 验证。

