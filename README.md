# PingPong Checkout / VCC 集成 POC

[![tests](https://github.com/jonji886/pingpong-checkout-vcc-integration-poc/actions/workflows/ci.yml/badge.svg)](https://github.com/jonji886/pingpong-checkout-vcc-integration-poc/actions/workflows/ci.yml)

> 基于 PingPong Checkout 公开资料和虚构客户 DemoAI 场景构建；当前为 **Mock Verified / Sandbox Pending**，不代表 PingPong 官方项目、真实客户案例或真实 Sandbox 联调经验。

## 项目定位

模拟一个 AI 平台接入跨境支付和虚拟卡能力的端到端 POC：

- 收款侧：Payment 创建、Query、Webhook、幂等、状态机、主动查单、退款和 Credits Ledger。
- 支出侧：VCC Workflow Assistant（可选 LLM 意图解析 + deterministic fallback）、预算校验、RBAC、人工审批、human confirmation、Mock/HTTP Issuing Adapter 和审计。
- 工程侧：Provider Adapter 隔离、失败路径、429/timeout、Webhook 重复与乱序、敏感字段脱敏。

本项目不处理真实资金，不采集或发送 PAN/CVV，不包含真实生产凭证，也不将 Mock 结果描述为 Sandbox 验证。

## 架构概览

```text
FastAPI API
    ↓
Application Services
    ↓
Domain State Machine + Idempotent Ledger
    ↓
Provider Ports
    ├── Mock Checkout / Issuing Adapter
    └── Current Unified Checkout / Issuing HTTP Adapter
             ↓
      Provider DTO / Mapper → Domain State Machine / Policy
```

SQLite 用于本地单实例演示。金额使用 `Decimal/Numeric`；Create Response、已验签 Webhook 和 Query/Reconciliation Observation 统一进入状态机，Credits 只通过 Ledger 入账。

## PingPong Sandbox Verification Status

| Capability | Contract | Mock E2E | Sandbox |
| --- | --- | --- | --- |
| Checkout Create / Session | ✅ | ✅ | ⏳ Provider Provisioning |
| Checkout Query | ✅ | ✅ | ⏳ Provider Provisioning |
| Checkout Refund | ✅ | ✅ | ⏳ Provider Provisioning |
| Checkout Webhook | ✅ | ✅ | ⏳ Local Simulation |
| VCC Create Card | ✅ | ✅ | ⏳ Provider Provisioning |
| VCC Card Query / Action / Transaction Query | ✅ | ✅ | ⏳ Provider Provisioning |

当前统一 Checkout / Issuing API 需要 PingPong 提供 Sandbox Account、API Credentials、签名密钥、产品配置和 callback 条件，因此本项目不宣称未验证的 Sandbox 能力。`CONTRACT_VERIFIED` 只表示官方公开字段已建模，并通过 fixture/MockTransport 检查请求序列化和响应解析。

## 快速运行（Mock）

环境要求：Python 3.10+。

```bash
cp .env.example .env
uv sync --extra test
python3 scripts/migrate.py
python3 -m uvicorn app.main:app --reload
```

另开一个终端验证创建充值订单：

```bash
curl -X POST http://127.0.0.1:8000/api/topups \
  -H 'Authorization: Bearer dev-token' \
  -H 'Idempotency-Key: demo-1' \
  -H 'Content-Type: application/json' \
  -d '{"amount":"100.00","currency":"USD"}'
```

也可以运行：

```bash
bash scripts/demo.sh
```

启动后访问：

- `/ui/demo`：Guided Demo 首页，按 AI Credits 收款或 VCC 企业支出开始体验。
- `/ui/developer`：业务友好的充值结果、Payment History、Provider / Webhook 失败实验、Payment Timeline。
- `/ui/finance`：按行查看交易、主动查单、Mock 失败实验室和带二次确认的全额退款。
- `/ui/fde`：按 Payment ID / Application ID / Trace ID 查询完整调用链和安全调试元数据。
- `/ui/vcc`：Step Flow 展示解析、Budget、RBAC、Approval、Human Confirmation 和 Mock 开卡。
- `/docs`：Swagger API 文档。

`/ui` 会默认跳转到 `/ui/demo`。页面顶部持续标明 `Environment: MOCK`、Contract / Mock E2E 验证状态和 `Sandbox: Pending Provider Provisioning`；Mock Verified 不代表真实 Sandbox 联调。

所有 UI 页面首屏均先说明当前角色、使用目的和下一步动作；“名词说明”可展开查看 Credits、Payment、VCC、Trace ID 等术语。页面文案以中文为主，关键 API / Provider 状态保留英文括注，方便新人上手后继续和接口、日志对照。

## Mock 演示流程

Mock Provider 支持确定性的 `PENDING`、`SUCCESS`、`FAIL`、`CLOSE`、`AUTH_SUCCESS`、`TIMEOUT` 和 `429` 行为。

1. 以 Developer 身份创建一笔 USD 充值订单。
2. 在 Developer 页面选择 Provider 创建场景，可以验证创建即失败、关闭、人工复核、超时和限流。`TIMEOUT` / `429` 会保持 `PROCESSING`，提示使用主动查单，不会新建交易。
3. 对 `PENDING` 订单，在“Webhook 测试结果”中选择 `SUCCESS`、`FAIL`、`CLOSE`、`AUTH_SUCCESS` 或非法状态；也可以点击“验签失败测试”，确认无效签名不会推进订单状态。

   也可以使用脚本发送签名 Webhook：

   ```bash
   python3 scripts/simulate_webhook.py "txn_${PAYMENT_ID}" --status SUCCESS --amount 100.00
   ```

   将 `PAYMENT_ID` 替换为创建订单返回的 Payment ID。

4. 查看 Payment 状态和 Credits 余额，重复发送同一 Webhook 验证幂等；失败、关闭和人工复核均不入账 Credits。
5. 在 Finance 页面切换 Mock Provider 场景后发起退款，观察退款失败、未知结果、Credit Hold 释放 / 保留。
6. 使用 FDE 页面或 `scripts/reconcile_due.py` 验证主动查单和丢失 Webhook 恢复。

## 本地演示身份

以下 Token 只用于本地 Mock，已经在浏览器 UI、测试和示例配置中公开，绝不能复用到任何真实环境：

| 角色 | Demo Token |
| --- | --- |
| Developer | `dev-token` |
| Finance | `finance-token` |
| Approver | `approver-token` |
| Admin / FDE | `admin-token` / `fde-token` |

Mock HMAC secret `local-demo-secret` 同样只是公开的本地演示值。生产环境应使用 OIDC/JWT、Secret Manager 和真实的 Provider 签名校验；前端暴露的 Demo Token 不具备安全性。

## Sandbox 边界

必须显式设置 `PINGPONG_MODE=mock|sandbox`，不会从 Sandbox 静默降级。Sandbox 模式启动时要求当前 Unified API 的 base URL、access token、sign-version、HTTPS 通知/回跳地址；缺少配置或使用示例保留域名会直接失败。`accId/clientId/salt` 仅属于显式 Legacy Adapter。

当前 Sandbox HTTP Adapter 使用官方统一 API 的 Hosted Session：`POST /api/acq/v4/sessions/create`，Query/Refund 使用 `/api/acq/v4/payments/query` 和 `/api/acq/v4/refunds/*`。它只创建客户动作 Session，不接收、不发送 PAN/CVV；支付终态仍来自已验签 Webhook 或 Query。当前统一 API 的请求头为 `Authorization`、`sign`、`sign-version`；签名实现以显式 `PingPongHeaderSigner` 注入，仓库不猜测 RSA/SM2 canonicalization。还需要产品权限、签名密钥、可访问 HTTPS callback 和商户配置；本仓库状态保持为 `SANDBOX_PENDING`。

历史公开 Checkout V4 `prePay` envelope (`/v4/payment/prePay`) 仍保留在 `PingPongSandboxCheckoutAdapter`，仅作为 `Legacy Public Sandbox` Contract 参考，不与当前统一 API 混用。契约边界见 [ADR-001](docs/adr/ADR-001-pingpong-checkout-v4-contract.md)。

参考官方资料：

- [PingPong Checkout V4 API overview](https://docs.pingpongx.com/api/acq/create-a-payment?version=v4)
- [PingPong Checkout V4 Create Session](https://docs.pingpongx.com/api/acq/payment/create-a-session?version=v4)
- [PingPong Issuing V2 Create a card](https://docs.pingpongx.com/api/issuing/cards/create-a-card?version=v2)
- [PingPong Issuing V2 Query card details](https://docs.pingpongx.com/api/issuing/cards/query-card-details?version=v2)
- [Checkout V4 endpoint guide](https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/guide/endpoint/)
- [Checkout V4 Hosted prePay](https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/checkout/api/reserve/)
- [Checkout V4 API-only unifiedPay](https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/checkout/api/uniformly/)
- [Checkout V4 API usage and signature rules](https://acquirer-api-docs-v4.pingpongx.com/en/notes/guide/APIUsage/)
- [Checkout V4 signature convention](https://acquirer-api-docs-v4.pingpongx.com/en/notes/guide/sign/)

## 测试

```bash
PINGPONG_MODE=mock PINGPONG_WEBHOOK_SECRET=local-demo-secret python3 -m pytest -q

# 只运行黑盒 HTTP E2E 验收
PINGPONG_MODE=mock PINGPONG_WEBHOOK_SECRET=local-demo-secret python3 -m pytest -m e2e
```

测试使用 Mock Adapter 和隔离数据库，不等同于真实 Sandbox 验证。

## 文档

`docs/` 包含客户场景、需求分析、方案设计、API 接入指南、支付状态机、Webhook 设计、VCC Workflow Assistant 设计、排障手册、测试计划、Go-live Checklist 和 [PRODUCT_FEEDBACK](docs/PRODUCT_FEEDBACK.md)。

`docs/adr/ADR-001-pingpong-checkout-v4-contract.md` 记录当前官方公开契约、已验证字段和 Sandbox Pending 边界。

VCC 自然语言解析默认可保持 deterministic；若配置 `LLM_ENABLED=true`，生产 ASGI app 使用 DeepSeek JSON Output 生成结构化申请。LLM 失败、超时或输出不合法时只返回 `NEEDS_CLARIFICATION`，不会触发预算、RBAC、审批、human confirmation 或开卡旁路。

## 仓库安全

`.env`、SQLite 数据库、缓存、虚拟环境和本地 `AGENTS.md` 已通过 `.gitignore` 排除。提交前仍应检查 staged 文件，避免手动上传这些文件或任何真实凭证、PII、Webhook 原文和支付动作 URL。
