# SPEC.md — DemoAI Global Payments & VCC Integration POC

> 版本：v1.5
> 状态：Implemented / Mock E2E Verified / Sandbox Pending
> 目标读者：AI Platform Developer / Finance / Approver / FDE / Solution Architect
> 语言：中文优先，关键 API、Provider 状态和技术名词保留英文

变更记录（v1.5，2026-09-06）：将文档从实施前计划调整为当前已实现能力说明；补充客户问题、证据等级、VCC 角色隔离和 Happy Path / Reliability Lab 展示边界。真实 PingPong Sandbox 仍未宣称完成。

## 0. 项目定位

DemoAI Global Payments & VCC Integration POC 用于验证 AI 平台客户接入支付能力时的业务流程、API 集成方案、异常恢复机制、企业支出控制与人工审批流程。

DemoAI 是虚构的 AI Model API 平台：全球开发者用 USD Credits 预充值，企业内部同时需要支付 AWS、Google Cloud、Datadog、GitHub 等全球云资源和 SaaS 费用。本项目是独立的技术 POC，不是 PingPong 官方项目，不代表真实客户案例或真实 Sandbox 联调；也可以作为 FDE 能力展示材料，但这不是系统设计目标。

## 1. 当前能力与证据等级

### 1.1 已实现能力

- Checkout Top-up：本地充值订单、Provider Create、Query、Webhook、状态机、Credits Ledger、主动查单、退款和基础对账视图。
- Reliability：Idempotency-Key、Webhook 验签、重复/乱序处理、金额/币种校验、Timeout / 429、失败路径、Reconciliation 和 Trace / Audit。
- Provider 隔离：Checkout / Issuing Port、Provider DTO / Mapper、确定性 Mock Adapter、当前 Unified HTTP Adapter 和 Legacy Contract 兼容边界。
- VCC Workflow：自然语言或确定性解析、Budget Check、Policy / RBAC、Approver 审批、Finance Human Confirmation、Mock Issuing Adapter 和脱敏卡记录。
- FDE 交付：Customer Scenario、Solution Design、API Integration Guide、状态机、Webhook、VCC、Troubleshooting、Test Plan 和 Go-live Checklist。
- Demo UI：Guided Demo、Developer Happy Path、可折叠 Reliability Lab、Finance 交易与退款、FDE 调试台、Finance / Approver 分角色 VCC 视图。

### 1.2 证据等级

```text
CONTRACT_VERIFIED
  官方公开 Contract 的 DTO / Mapper / fixture / MockTransport 请求序列化与响应解析检查。

MOCK_E2E_VERIFIED
  本地 Mock Provider、Webhook、状态机、Ledger、退款、VCC Workflow 和自动化测试闭环。

SANDBOX_PENDING
  尚无合法 Sandbox Account、Credentials、产品权限、签名密钥和公网 HTTPS callback 的真实验证证据。
```

`CONTRACT_VERIFIED` 或 `MOCK_E2E_VERIFIED` 都不等于真实 Sandbox 联调。README、UI 和文档必须持续保留这个边界。

## 2. 业务范围

### 2.1 P0：Credits 收款闭环

- 创建充值订单和 Payment。
- 使用 Provider Create Response、已验签 Webhook、Query / Reconciliation 作为可信 Provider Observation。
- 通过同一 Payment State Machine 映射 Provider 状态，成功时通过唯一约束保护的 TOPUP Ledger 入账一次。
- 支持 Webhook 重复、乱序、延迟、丢失、无效签名、未知订单、金额/币种不匹配。
- Create Timeout / 429 的结果未知时保持 `PROCESSING`，使用原有关联 ID 查单，不创建第二笔逻辑交易。
- 支持全额 Refund、Refund Query、CreditHold 结算/释放和余额不足的 `MANUAL_REVIEW`。
- 提供 Payment Timeline、Provider Call、Webhook、Audit 和基础 Reconciliation 视图。

### 2.2 P1：企业 VCC Workflow

```text
Finance Requester
  → Structured Parsing
  → Budget Check
  → Policy / RBAC
  → Approver 批准或拒绝
  → Finance / Authorized Operator Human Confirmation
  → Mock Issuing Adapter
```

- LLM（如果启用）只负责不可信的结构化解析；解析失败进入 `NEEDS_CLARIFICATION`。
- Budget、Policy、RBAC、Approval、Human Confirmation 和 Provider 调用由后端确定性代码执行。
- `Finance` 只能提交申请和在批准后执行最终开卡；`Approver` 才能批准/拒绝。
- UI Persona 切换只用于 Demo，不改变后端 Principal；审批接口必须使用 Approver 权限。
- Card detail 只返回脱敏卡号，不保存或返回 PAN/CVV。

### 2.3 P2：明确不实现

- 真实资金、真实生产 VCC 发卡、真实 KYC/KYB、PCI DSS 卡数据存储。
- Production IAM / Enterprise SSO、完整组织审批委派、多租户 SaaS。
- 复杂 FX、自动续费、Chargeback / Dispute、真实清结算。
- 智能支付路由、Stripe / Adyen 等多 Provider Router、自动 Fallback。
- Production HA/DR、消息队列、大规模压测平台和多 Agent 系统。
- 未取得权限或未完成真实外部调用的 PingPong Sandbox 验证。

## 3. Personas 与权限

| Persona | 目标 | 当前最小权限 |
| --- | --- | --- |
| Developer | 充值 Credits，查看本人 Payment 和余额 | `POST /api/topups`、本人查询 |
| Finance / Requester | 查看交易、退款、提交 VCC、批准后开卡 | Finance 资源与本人 VCC 申请 |
| Approver | 审核并批准/拒绝 VCC 申请 | `POST /api/vcc/{id}/approve` |
| FDE / Admin | 对账、Debug、Webhook、审计和 Mock 场景 | Admin/FDE 运维接口 |

所有受保护 API 从认证 Bearer Principal 获取 `actor_id` 和 `role`，不信任请求体、Query 或 Header 中自报的身份。普通 Developer 不得读取企业 VCC 申请；Finance、Approver、Admin/FDE 的 API 权限在路由层重新校验。

## 4. 核心业务规则

### 4.1 Payment 与 Credits

1. 金额使用 `Decimal / NUMERIC`，首期只支持 USD。
2. Create Response、已验签 Webhook、Query / Reconciliation Response 必须统一进入 `Trusted Provider Observation → Provider Mapper → Domain State Machine → Exactly-once Ledger`。
3. 前端 redirect / callback / success page 只能表示客户下一步动作，不能决定支付终态或 Credits 入账。
4. Provider `SUCCESS` 映射为本地 `SUCCEEDED`，TOPUP Ledger 在数据库唯一约束下最多产生一次业务效果。
5. `PENDING / PROCESSING` 映射为 `PROCESSING`；`FAIL / FAILED` 映射为 `FAILED`；`CLOSE / CLOSED / CANCEL` 映射为 `CANCELLED`；`AUTH_SUCCESS` 映射为 `REVIEW_REQUIRED`。
6. 最终状态不会因重复或乱序 Observation 回退。

### 4.2 Timeout、Retry 与 Reconciliation

- Timeout / Connection Error 不等于 Provider 失败，也不等于远端未受理。
- Create 结果未知时不自动创建第二笔 Payment；保留原 `partner_transaction_id`、`provider_request_id`，通过 Query / Reconciliation 恢复。
- 只有明确可安全重试的 Query、Refund Query 或受 Provider 幂等约束保护的调用才允许 bounded retry；不无限重试。
- Webhook 不是唯一一致性来源；后台扫描和人工 `POST /api/admin/payments/{id}/reconcile` 可恢复滞后状态。

### 4.3 Refund

`RefundOrder` 与 Payment 生命周期独立。P0 只支持全额退款，一个 Payment 最多一个 RefundOrder：

```text
CREATED → PROCESSING → SUCCEEDED | FAILED
                              └→ MANUAL_REVIEW（业务前置条件不满足）
```

退款前先检查可用 Credits 并创建 `CreditHold`；Provider 成功后写负向 `REFUND_REVERSAL` Ledger 并结算 Hold，失败或结果明确未受理时释放 Hold。Credits 不足时进入 `MANUAL_REVIEW`，不得调用 Provider 退款 API，也不得产生负余额。Payment 成功事实不因退款改变，UI 可派生显示 `REFUNDED`。

### 4.4 VCC 安全边界

高风险顺序固定为：

```text
Authentication → Authorization → Current State → Budget / Policy
→ Approver Approval → Human Confirmation → Idempotency → Provider → Audit
```

LLM 不决定最终权限、预算、审批或开卡；不读取 Provider Secret；不能直接调用 PingPong Client 或修改审批状态。申请人和审批人必须在 UI 与后端职责上分离。

## 5. Provider Contract 边界

- 业务 Service 只依赖 `CheckoutProvider` / `IssuingProvider` Port，不读取 PingPong 原始 envelope。
- Adapter 负责鉴权、HTTP、签名、DTO、Mapper、错误分类和敏感字段丢弃。
- 当前统一 Checkout 主路径是 Hosted Session / Query / Refund 的 Adapter；历史 `/v4/payment/*` 代码只作为 Legacy Contract 保留，不与当前 unified API 混用。
- Issuing Adapter 覆盖公开文档中已建模的 card apply、card detail、freeze/unfreeze/close、spending control、balance 和 authorization query；真实卡产品权限仍为 Pending。
- `PINGPONG_MODE=mock|sandbox` 必须显式设置；禁止 Sandbox 静默降级到 Mock。
- Sandbox 的 endpoint、产品、callback、账户级验签方式、签名 canonicalization 和字段细节必须以当前官方文档与账户契约为准，无法确认时 fail closed，不猜测。

当前仓库的外部资料基线记录在 [ADR-001](docs/adr/ADR-001-pingpong-checkout-v4-contract.md) 和 [API Integration Guide](docs/04-api-integration-guide.md)；这些资料不构成真实 Sandbox 验证证据。

## 6. API 与演示边界

### 6.1 关键 API

| 能力 | API |
| --- | --- |
| 创建充值 | `POST /api/topups`，必须带 `Idempotency-Key` |
| Payment Query | `POST /api/payments/{id}/query` |
| Checkout Webhook | `POST /api/webhooks/pingpong/checkout` |
| 退款 | `POST /api/refunds`，必须带 `Idempotency-Key` |
| 主动对账 | `POST /api/admin/payments/{id}/reconcile` |
| VCC 申请 | `POST /api/vcc/agent`，Finance/Admin |
| VCC 审批 | `POST /api/vcc/{id}/approve`，Approver/Admin |
| VCC 开卡 | `POST /api/vcc/{id}/card`，Finance/Admin + Human Confirmation |

### 6.2 UI 信息架构

- Guided Demo 首页先解释两条业务链路。
- Developer 默认只展示 `100.00 USD` 和“创建充值”；正常路径是 Create Checkout → Payment → Webhook / Query → Credits。
- Provider Create、Webhook 状态注入、重复/无效签名、金额不匹配、Timeout、429、Reject、Manual Review 等进入可折叠 `Reliability Lab`。
- VCC Finance 视图显示“申请已提交 / 等待审批 / 申请人 Finance / 审批人 Approver”；Approver 视图提供独立的“批准 / 拒绝”；批准后回到 Finance 执行最终确认。
- UI 的 Mock Token 仅用于本地演示，不能用于生产；环境、Contract、Mock E2E、Sandbox 状态必须持续可见。

## 7. 自动化验证

当前测试必须覆盖并持续保持：

- Happy Path：创建、可信成功 Observation、Credits 入账一次、Query、全额 Refund。
- Failure Path：FAIL、CLOSE、AUTH_SUCCESS、TIMEOUT、429、无效签名、未知状态、未知订单、金额/币种不匹配。
- Idempotency / Concurrency：重复 API、payload 冲突、重复 Webhook、乱序 Observation、Webhook 与 Query 并发、Ledger 唯一约束。
- Refund：重复退款、CreditHold、余额不足、失败释放和未知结果 Query。
- VCC：缺字段、预算拒绝、越权审批 403、审批前不可开卡、Human Confirmation、脱敏和 Audit。
- Security：认证、RBAC、敏感字段和 Provider 原始 body / signature 不进入日志或持久化记录。
- Contract：fixture、DTO / Mapper、MockTransport 和 Adapter 请求序列化；不将这些测试写成 Sandbox E2E。

验证命令：

```bash
uv run pytest
uv run pytest -m e2e
```

## 8. 文档交付物

- [Customer Scenario](docs/01-customer-scenario.md)：客户背景、痛点、Persona、业务流程、POC Questions、验收和 Out of Scope。
- [Requirement Analysis](docs/02-requirement-analysis.md)
- [Solution Design](docs/03-solution-design.md)
- [API Integration Guide](docs/04-api-integration-guide.md)
- [Payment State Machine](docs/05-payment-state-machine.md)
- [Webhook Design](docs/06-webhook-design.md)
- [VCC Agent Design](docs/07-vcc-agent-design.md)
- [Troubleshooting](docs/08-troubleshooting.md)
- [Test Plan](docs/09-test-plan.md)
- [Go-live Checklist](docs/10-go-live-checklist.md)

## 9. Definition of Done

- [x] 当前 P0/P1 代码、Mock E2E 和文档可运行、可检查。
- [x] Mock / Contract / Sandbox 证据等级在 API、UI、README 和文档中保持区分。
- [x] Payment、Refund、VCC 状态机、幂等、审批、Human Confirmation 和 Audit 规则有自动化测试。
- [x] UI 首屏优先表达业务价值，异常能力位于 Reliability Lab，VCC 展示职责分离。
- [ ] 真实 PingPong Sandbox Checkout / Issuing 全链路验证；该项依赖外部账户、权限、凭证和 callback，当前保持 Pending。
- [ ] Production IAM、Secret Manager、Webhook Secret Rotation、PostgreSQL 锁策略、HA/DR 和真实运营配置。

## 10. 当前限制

SQLite 仅支持本地单实例演示；本地 Bearer Token、公开 Mock HMAC Secret、确定性 Provider 和截图都只服务于 POC。没有真实 Sandbox 证据时，任何交付材料都不得使用“已完成 PingPong Sandbox 联调”等表述。
