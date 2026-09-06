# 客户场景：DemoAI 全球收款与企业支出

> Change Risk: LOW。本文定义客户问题与 POC 验收边界，不把 Mock 或 Contract Test 描述为真实 Sandbox 联调。

## 1. Customer Background

DemoAI 是一个面向全球开发者提供 AI Model API 的平台：开发者通过 USD Credits 预充值，再消费模型 API。企业内部同时需要支付 AWS、Google Cloud、Datadog、GitHub 等全球云资源和 SaaS 费用，财务希望建立一条可控、可追踪的企业支出流程。

本 POC 首期只实现 USD，定价规则为 `1.00 USD = 1.00 USD_CREDIT`。项目不处理真实资金，不采集或发送 PAN/CVV，也不代表 PingPong 官方项目或真实客户案例。

## 2. Current Pain Points

### Developer Payment

- 全球开发者需要统一的 Credits 充值入口。
- 前端 redirect 只能代表客户下一步动作，不能作为支付成功事实。
- Create Timeout 后无法确认 Provider 是否受理，不能盲目创建第二笔交易。
- Webhook 可能重复、延迟、乱序或丢失。
- Credits 必须只入账一次，并能通过 Query / Reconciliation 恢复未知状态。

### Enterprise VCC

- AI 可以理解员工的自然语言付款需求，但不能直接拥有企业资金操作权限。
- 支出申请必须经过预算、Policy、RBAC 和人工审批。
- 申请人不能自己完成 Approver 操作；审批通过后仍需要 Finance / Authorized Operator 做最终 Human Confirmation。
- 高风险动作需要保留 Trace ID、审批记录和开卡 Audit，方便 FDE 排障与复核。

## 3. Personas

### Developer

目标：充值 Credits，并确认 Payment 最终状态与余额入账结果。

### Finance（Requester）

目标：提交企业云资源或 SaaS 的用卡申请，查看审批状态，并在批准后完成最终人工确认。

### Approver

目标：独立核对商户、金额、用途、Budget / Policy 结果，批准或拒绝 VCC 申请。

### FDE / Admin

目标：用 Payment ID、Application ID 或 Trace ID 定位 API、Provider、Webhook、状态机、Ledger 和 Audit 问题。

## 4. Business Flow

### Flow A：Developer Credits Top-up

```text
Developer
  → Create Checkout / Payment
  → Provider
  → Verified Webhook 或 Query / Reconciliation
  → Payment State Machine
  → Exactly-once Credit Ledger
```

### Flow B：Enterprise VCC

```text
Finance Requester
  → AI / Deterministic Structured Parsing
  → Budget Check
  → Policy / RBAC Check
  → Approver 批准或拒绝
  → Finance Human Confirmation
  → Mock Issuing Adapter 创建脱敏卡记录
```

两个流程共享 Adapter、Trace、Audit 和失败恢复的工程原则，但 Payment 状态机与 VCC Approval / Card 生命周期保持独立。

## 5. POC Questions

1. AI 平台如何安全地为全球开发者提供 Credits 充值？
2. Create Timeout 后如何避免重复创建交易？
3. Webhook 重复、乱序或丢失时，如何保证业务结果正确？
4. Credits 为什么不能简单依赖一次 Webhook 执行 `balance += amount`？
5. AI 如何参与企业 VCC 流程，同时无法绕过预算、Policy、RBAC 和审批？
6. FDE 如何快速判断问题发生在 API、Provider、Webhook、Ledger 还是业务状态机？

## 6. Acceptance Criteria

### Checkout Success

```text
Given Developer 创建 100 USD Credits 充值
When Provider 的可信 Observation 最终确认支付成功
Then Payment 状态为 SUCCEEDED
And Credits 只增加一次
```

### Duplicate Webhook

```text
Given 一笔成功交易已完成入账
When 同一 Webhook 被重复投递
Then 请求可以安全确认
And Credits 不得重复增加
```

### Create Timeout

```text
Given Provider Create 请求发生 Timeout
When 系统无法确认交易是否创建成功
Then Payment 保持 PROCESSING
And 不立即创建第二笔交易
And 使用原有 Provider request / transaction 关联信息进行 Query / Reconciliation
```

### VCC Role Separation

```text
Given Finance 提交一笔需要审批的 VCC 申请
When Finance 尝试调用 Approver 操作
Then 后端拒绝该操作并返回 403
When Approver 批准申请
Then Finance 才能进入最终 Human Confirmation 和开卡步骤
```

### AI Safety Boundary

```text
Given AI 成功解析出支付金额、商户和用途
When 请求进入资金控制流程
Then Budget / Policy / RBAC / Approval 仍由确定性后端执行
And LLM 输出不能直接触发资金动作
```

### Evidence Boundary

```text
Given 当前仓库没有合法 PingPong Sandbox 凭证、产品权限和 callback 前置条件
When 展示项目能力
Then 只能声明 Contract Verified / Mock E2E Verified
And Sandbox 必须保持 Pending，不得包装为真实联调
```

## 7. Out of Scope

- 真实资金、真实生产 VCC 发卡或真实卡片敏感信息。
- Production KYC / KYB、PCI DSS、完整清结算、FX、Chargeback / Dispute。
- Production HA / DR、多租户 SaaS、复杂支付路由和大规模压测。
- Production IAM、Enterprise SSO 和完整组织级 Approver 委派体系。
- 未取得权限的 PingPong Sandbox 联调与真实 Sandbox 验证结论。

## 8. Current Evidence

```text
Contract Verified：官方公开字段的 DTO / Mapper / fixture / MockTransport 检查
Mock E2E Verified：本地 Mock Provider、Webhook、Ledger、VCC Workflow 与自动化测试
Sandbox Pending：等待合法账户、凭证、签名密钥、产品权限与 callback 条件
```
