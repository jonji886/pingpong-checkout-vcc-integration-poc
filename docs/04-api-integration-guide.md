# API Integration Guide

目标读者：第一次运行 DemoAI POC 的客户后端工程师。

## Evidence Status

```text
MOCK_VERIFIED       本地业务闭环、失败注入和自动化测试
CONTRACT_VERIFIED   官方公开 V4 fixture + DTO/Mapper + MockTransport
SANDBOX_PENDING     本仓库没有宣称真实成功 Sandbox E2E
```

## Prerequisites

- Python 3.10+（CI 使用 Python 3.11）。
- 本地 SQLite；无需真实 PingPong credential。
- `PINGPONG_MODE=mock`，不要把本地 `.env` 改成 Sandbox 后期待自动完成联调。

```bash
cp .env.example .env
python3 -m pip install -e '.[test]'
python3 scripts/migrate.py
PINGPONG_MODE=mock PINGPONG_WEBHOOK_SECRET=local-demo-secret python3 -m uvicorn app.main:app --reload
```

## Authentication

本地 Demo API 使用 `.env` 中的演示 Bearer token，仅用于 POC：

| API principal | Token | 权限 |
| --- | --- | --- |
| Developer | `dev-token` | 本人充值、查余额、查本人 Payment |
| Finance | `finance-token` | 退款、VCC 申请 |
| Approver | `approver-token` | VCC 审批 |
| Admin/FDE | `admin-token` / `fde-token` | Debug、Webhook、对账 |

这套 token 不是 PingPong Provider Auth。当前统一 API 使用 `Authorization`、`sign`、`sign-version`；签名由 infrastructure signer 注入 Adapter，不能根据其他平台猜 canonicalization。Secret 不进入业务服务、日志或前端。

## Integration Flow

### 1. Create Topup

```bash
curl -sS -X POST http://127.0.0.1:8000/api/topups \
  -H 'Authorization: Bearer dev-token' \
  -H 'Idempotency-Key: customer-order-001' \
  -H 'Content-Type: application/json' \
  -d '{"amount":"100.00","currency":"USD"}'
```

返回 `payment_id`、`payment_status` 和统一的 `next_action`。`next_action.type` 可能是 `REDIRECT`、`QR_CODE` 或 `NONE`；客户端不得假设存在 `checkout_url`。

### 2. 等待 Webhook 或主动 Query

```bash
curl -sS http://127.0.0.1:8000/api/payments/{payment_id} \
  -H 'Authorization: Bearer dev-token'

curl -sS -X POST http://127.0.0.1:8000/api/payments/{payment_id}/query \
  -H 'Authorization: Bearer dev-token'
```

只有服务端已认证 Create response、已验签 Webhook 或 Query/Reconciliation 才能将 Payment 置为终态并发放 Credits。前端 redirect 不是支付事实来源。

### 3. 本地 Mock Webhook

```bash
python3 scripts/simulate_webhook.py txn_{payment_id} --status SUCCESS --amount 100.00
```

重复发送相同通知只返回成功确认，不产生第二笔 TOPUP ledger。当前公开 Checkout webhook 是 flat payment/refund event；本仓库通过显式注入的 `PingPongWebhookVerifier` 执行验签，未确认账户级验签方式时 Sandbox webhook 会 fail closed。Mock 的 `X-Mock-Signature` 只属于 deterministic test contract。

### 4. Inspect Payment

```bash
curl -sS http://127.0.0.1:8000/api/payments/{payment_id} \
  -H 'Authorization: Bearer dev-token'
```

重点关联字段：`local payment_id`、`partner_transaction_id`、`provider_request_id`、`provider_transaction_id`、`payment_status`。

### 5. Refund

```bash
curl -sS -X POST http://127.0.0.1:8000/api/refunds \
  -H 'Authorization: Bearer finance-token' \
  -H 'Idempotency-Key: refund-001' \
  -H 'Content-Type: application/json' \
  -d '{"payment_id":"{payment_id}"}'
```

P0 只支持全额退款。退款本地先创建 `RefundOrder + CreditHold`，Provider call 在 DB transaction 外；成功后写负向 `REFUND_REVERSAL` ledger，失败释放 hold。

## Idempotency

- Client → DemoAI：`POST /api/topups` 和 `POST /api/refunds` 必须传 `Idempotency-Key`。同一 principal、route、key、payload replay 原响应资源；相同 key 不同 payload 返回 `409`。
- DemoAI → PingPong：Checkout V4 API-only 使用 `merchantTransactionId + requestId` 作为请求识别/幂等组合。本地 timeout 后必须复用同一组合进行 Query Recovery，不能新建逻辑 Payment。
- Webhook Layer A：官方公开 notification 字段没有稳定 event ID，因此本地命名为 `delivery_fingerprint`；它是 canonical payload hash，不等同 Provider event ID。
- Webhook Layer B：Payment 状态机单调性与 `CreditLedger` 唯一约束保护业务效果。

## Correlation IDs

```text
trace_id                 一次本地请求/后台动作
local_payment_id         PaymentOrder 主键
request_id               本地生成的 Provider request identifier
partner_transaction_id   本地生成、发送给 Provider 的 merchant order number
transaction_id           Provider 返回的交易编号
refund_id                本地 RefundOrder 主键
partner_refund_id        发送给 Provider 的 merchant refund number
provider_call_id         本地 ProviderCallLog 主键
delivery_fingerprint     无官方 event ID 时的本地 webhook 去重值
```

## Current Unified Provider Contract Boundary

本次可读取的公开 V4 开发文档使用：

```text
POST /api/acq/v4/sessions/create       # 本 POC 使用：Hosted Checkout Session
POST /api/acq/v4/payments/query
POST /api/acq/v4/refunds/create
POST /api/acq/v4/refunds/query
```

统一 API 返回 `{code,message,data}`。Session 返回的 `action.redirect_url` 只代表客户动作；Session 创建成功不代表付款成功。Query/Webhook 才能推进支付状态；本 POC 不采集或发送 PAN/CVV。直接 Create Payment 的卡数据路径不由本 POC 调用。具体商户的 callback、signer、enabled product 仍需账户契约确认。详见 [ADR-001](adr/ADR-001-pingpong-checkout-v4-contract.md)。

历史公开 `prePay` envelope 代码和 fixture 仍保留，但标记为 `Legacy Public Sandbox`，不与当前 unified API 混用。

### Issuing v2 HTTP Adapter

当前 HTTP Adapter 已实现官方公开的：

- `POST /api/issuing/card/v2/apply`：Create Card，需要配置 `PINGPONG_ISSUING_CARD_PRODUCT_CODE`。
- `GET /api/issuing/card/v2/detail`：Query Card Detail。
- `POST /api/issuing/card/v2/freeze|unfreeze|close`：Card Action。
- `POST /api/issuing/spending-control/v2/share-card-limit`：Control Spending。
- `GET /api/issuing/card/v2/normal/balance`：Query Dedicated Funds Card balance。
- `GET /api/issuing/transaction/v2/authorizations`：Query authorization logs。

Create/Action/Spending Control 使用签名头；Query 类接口只使用官方要求的 Authorization。Card detail 中的 PAN/CVC 在 Adapter boundary 丢弃。Issuing 具体卡产品和 Sandbox 权限仍为 Pending。

## Status Mapping

| Provider status | Domain status | Credits |
| --- | --- | --- |
| `INIT` | `CREATED` | no |
| `PENDING` / `PROCESSING` | `PROCESSING` | no |
| `SUCCESS` | `SUCCEEDED` | TOPUP once |
| `FAILED` / `FAIL` | `FAILED` | no |
| `CANCEL` / `CLOSED` / `CLOSE` | `CANCELLED` | no |
| `AUTH_SUCCESS` | `REVIEW_REQUIRED` | no |

Refund 是独立状态机：`CREATED → PROCESSING → SUCCEEDED|FAILED`；余额不足为 `MANUAL_REVIEW`。

## Error Handling

| HTTP/provider situation | Local behavior |
| --- | --- |
| 400 | `ProviderRejected`，不重试，检查字段/商户产品 |
| 401/403 | `ProviderAuthError`，不重试，检查 Authorization/sign/sign-version/权限 |
| 409 | 幂等或业务冲突，复用原资源或人工检查，不生成新交易 |
| 429 | `ProviderRateLimited`，读取 `Retry-After`，bounded backoff；不无限重试 |
| 5xx | `ProviderUnavailable`，Query 可有限重试；Create 结果未知时先 Query |
| network timeout | `ProviderTimeout`，Create 保持 PROCESSING；Query Recovery |

## Webhook Requirements

1. 使用 HTTPS/public callback；原始 body 先验签。
2. Sandbox current Unified Webhook 使用显式注入的账户级 verifier；未配置 verifier 时返回 503 并不执行业务逻辑。Mock 使用本地 HMAC，仅限本地。
3. 验签失败返回 401；合法但未知订单/状态/金额 mismatch 写安全事件并安全确认。
4. 对 `provider_event_id`（仅官方明确提供时）或 `delivery_fingerprint` 建唯一约束。
5. 业务处理完成后 ACK；真实 Provider 重试策略以当前官方文档和账户契约为准。
6. Webhook 丢失时由后台/人工 Query 补偿。

## Mock vs Sandbox

Mock Adapter、fixture、MockTransport 和固定样例测试都不能称为真实 Sandbox。当前仓库状态：`MOCK_VERIFIED` + `CONTRACT_VERIFIED` + `SANDBOX_PENDING`；没有在本文中把 contract test 写成真实联调。
