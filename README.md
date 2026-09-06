# PingPong Checkout / VCC 集成 POC

[![tests](https://github.com/jonji886/pingpong-checkout-vcc-integration-poc/actions/workflows/ci.yml/badge.svg)](https://github.com/jonji886/pingpong-checkout-vcc-integration-poc/actions/workflows/ci.yml)

> 基于 PingPong Checkout 公开资料和虚构客户 DemoAI 场景构建；当前为 **Mock Verified / Sandbox Pending**，不代表 PingPong 官方项目、真实客户案例或真实 Sandbox 联调经验。

## 项目定位

模拟一个 AI 平台接入跨境支付和虚拟卡能力的端到端 POC：

- 收款侧：Payment 创建、Query、Webhook、幂等、状态机、主动查单、退款和 Credits Ledger。
- 支出侧：VCC Workflow Assistant（可选 LLM 意图解析 + deterministic fallback）、预算校验、RBAC、人工审批、Mock 开卡和审计。
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
    └── Sandbox Checkout HTTP Adapter（Hosted prePay / Query / Refund）
```

SQLite 用于本地单实例演示。金额使用 `Decimal/Numeric`；Create Response、已验签 Webhook 和 Query/Reconciliation Observation 统一进入状态机，Credits 只通过 Ledger 入账。

## 验证状态

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Checkout Mock | `MOCK_VERIFIED` | 本地 Mock、单元测试和 HTTP E2E 已覆盖 |
| Checkout public Contract | `CONTRACT_VERIFIED` | 官方公开 V4 fixture、DTO/Mapper 和 MockTransport 已覆盖；不等于真实 API 调用 |
| Checkout Sandbox | `SANDBOX_PENDING` | 已对公用网关和 API-only `unifiedPay` 做过外部烟测；该账号返回 `500008`（无可用 subChannel）并确认为 `FAILED`。项目 Adapter 走 Hosted `prePay`，尚未完成成功支付、回调和退款全链路 |
| VCC Issuing / Workflow Assistant | `MOCK_ONLY` | 可选 LLM 仅做结构化提取；预算、RBAC、审批和开卡仍由后端确定性控制，不代表真实发卡 |

## 快速运行（Mock）

环境要求：Python 3.9+。

```bash
cp .env.example .env
python3 -m pip install -e '.[test]'
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

- `/ui/developer`：充值、Payment History、模拟成功 Webhook。
- `/ui/finance`：交易查询和退款。
- `/ui/fde`：主动查单、Provider Calls、Webhook Events、Audit Log。
- `/ui/vcc`：VCC Workflow Assistant、预算检查、人工审批和 Mock 开卡。
- `/docs`：Swagger API 文档。

## Mock 演示流程

Mock Provider 支持确定性的 `PENDING`、`SUCCESS`、`FAIL`、`TIMEOUT` 和 `429` 行为。

1. 以 Developer 身份创建一笔 USD 充值订单。
2. 在 Developer 页面点击“模拟 SUCCESS Webhook”，或使用脚本发送签名 Webhook：

   ```bash
   python3 scripts/simulate_webhook.py "txn_${PAYMENT_ID}" --status SUCCESS --amount 100.00
   ```

   将 `PAYMENT_ID` 替换为创建订单返回的 Payment ID。

3. 查看 Payment 状态和 Credits 余额，重复发送同一 Webhook 验证幂等。
4. 在 Finance 页面发起退款，观察 Credit Hold、退款状态和余额变化。
5. 使用 FDE 页面或 `scripts/reconcile_due.py` 验证主动查单和丢失 Webhook 恢复。

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

必须显式设置 `PINGPONG_MODE=mock|sandbox`，不会从 Sandbox 静默降级。Sandbox 模式启动时要求 base URL、`accId/clientId/salt`、HTTPS 通知/回跳地址和 shopper IP；缺少配置或使用示例保留域名会直接失败。

仓库中的 Sandbox HTTP Adapter 使用官方 V4 Hosted `prePay`，只创建支付订单并返回 Hosted `paymentUrl`，不接收、不发送 PAN/CVV；支付完成后由 Webhook 或 Query 进入本地状态机。API-only `unifiedPay` 是另一条需要卡数据/PCI 约束的路径，不属于本 POC。仅填入 `accId`、`clientId`、salt 仍不足以完成真实联调，还需要商户可访问的 HTTPS 通知、支付结果/取消地址、有效 shopper IP，以及已开通的 Hosted 产品权限；本仓库状态保持为 `SANDBOX_PENDING`。契约边界见 [ADR-001](docs/adr/ADR-001-pingpong-checkout-v4-contract.md)。

参考官方资料：

- [PingPong Checkout V4 API overview](https://docs.pingpongx.com/api/acq/create-a-payment?version=v4)
- [Checkout V4 endpoint guide](https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/guide/endpoint/)
- [Checkout V4 Hosted prePay](https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/checkout/api/reserve/)
- [Checkout V4 API-only unifiedPay](https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/checkout/api/uniformly/)
- [Checkout V4 API usage and signature rules](https://acquirer-api-docs-v4.pingpongx.com/en/notes/guide/APIUsage/)
- [Checkout V4 signature convention](https://acquirer-api-docs-v4.pingpongx.com/en/notes/guide/sign/)

## 测试

```bash
PINGPONG_MODE=mock PINGPONG_WEBHOOK_SECRET=local-demo-secret python3 -m pytest

# 只运行黑盒 HTTP E2E 验收
PINGPONG_MODE=mock PINGPONG_WEBHOOK_SECRET=local-demo-secret python3 -m pytest -m e2e
```

测试使用 Mock Adapter 和隔离数据库，不等同于真实 Sandbox 验证。

## 文档

`docs/` 包含客户场景、需求分析、方案设计、API 接入指南、支付状态机、Webhook 设计、VCC Workflow Assistant 设计、排障手册、测试计划和 Go-live Checklist。

`docs/adr/ADR-001-pingpong-checkout-v4-contract.md` 记录当前官方公开契约、已验证字段和 Sandbox Pending 边界。

VCC 自然语言解析默认可保持 deterministic；若配置 `LLM_ENABLED=true`，生产 ASGI app 使用 DeepSeek JSON Output 生成结构化申请。LLM 失败、超时或输出不合法时只返回 `NEEDS_CLARIFICATION`，不会触发预算、审批或开卡旁路。

## 仓库安全

`.env`、SQLite 数据库、缓存、虚拟环境和本地 `AGENTS.md` 已通过 `.gitignore` 排除。提交前仍应检查 staged 文件，避免手动上传这些文件或任何真实凭证、PII、Webhook 原文和支付动作 URL。
