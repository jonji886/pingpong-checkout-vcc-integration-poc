# Go-live Checklist

- [ ] 已确认官方 Checkout V4 账户契约、鉴权/签名、支付动作和状态枚举。
- [ ] 已配置 HTTPS notify URL、合法 Sandbox 凭证和产品权限。
- [ ] 已验证 Create → Query/Webhook → Refund，并保存去敏证据。
- [ ] 已验证幂等、重放、乱序、查单、429/timeout 和审计告警。
- [ ] 已确认不采集 PAN/CVV，不把 Secret、PII、payload 或动作 URL 写入日志。
- [ ] README 的 Mock/Sandbox 验证状态与实际证据一致。

