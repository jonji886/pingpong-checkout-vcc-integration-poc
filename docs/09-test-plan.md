# Test Plan

必须覆盖状态迁移、Ledger/Hold 幂等、重复/乱序/延迟 Webhook、查单恢复、失败、退款与重复退款、余额不足、timeout、429、签名失败、幂等 payload 冲突、并发入账、RBAC 及敏感字段脱敏。Mock Adapter + Test DB 用于业务集成；Sandbox 只做无 Secret 的 MockTransport 协议映射测试，真实联调不属于 CI。

