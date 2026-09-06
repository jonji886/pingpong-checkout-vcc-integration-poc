# VCC Workflow Assistant Design

当前实现选择“确定性后端 + 可选 LLM Parser”的 `VCC Workflow Assistant`。默认测试和无 LLM 配置时使用 deterministic parser；设置 `LLM_ENABLED=true` 后，生产 ASGI app 可使用 DeepSeek JSON Output 做自然语言结构化提取。两种 Parser 都不拥有审批、开卡或 Provider Secret，也不宣称真实 PingPong Issuing Sandbox 发卡。

## Boundary

```text
Natural Language Request
        ↓
RuleBasedIntentParser / Optional LLMIntentParser
        ↓
Structured PaymentRequest
        ↓
Deterministic Budget / RBAC / Approval Policy
        ↓
Human Approval（金额超过 1,000 USD）
        ↓
IssuingService Tool Boundary
        ↓
Mock IssuingProvider
        ↓
AuditLog
```

Parser 只提取 `vendor`、`amount`、`currency`、`purpose`、`period_days`。缺失金额/币种时返回 `missing_fields`，不猜业务金额；金额、币种、预算、审批和当前状态由后端重新校验。LLM 输出使用 JSON mode 并经过 Pydantic 和 Decimal/币种/期限校验。

## Security Invariants

- Parser 不能决定最终预算、RBAC 或审批结果。
- Finance 不能绕过 Approver 创建高金额 VCC；`IssuingService` 再次检查 `APPROVED`/`AUTO_APPROVED` 状态。
- Provider secret 只属于 Infrastructure/Config，不进入 parser 或 tool response。
- Mock card 只返回 masked value，不保存 PAN/CVV。
- 申请、审批、开卡均写 AuditLog，并带 `trace_id`。
- LLM 只接收自然语言申请，不接收 PAN/CVV、Provider Secret 或审批上下文中的敏感信息。
- LLM parsing failure、超时或非法 JSON 必须进入 `NEEDS_CLARIFICATION`，不能静默回退为一笔可执行申请。
- `LLM_ENABLED=false` 时完全不依赖外部模型；Contract Test 和 CI 使用 Rule/Fake Parser。

## Domain Lifecycle

```text
DRAFT → PENDING_APPROVAL → APPROVED → CARD_CREATING → ACTIVE → CLOSED
                    └──────→ REJECTED
```

预算为 50,000 USD、已用 10,000 USD；超过 1,000 USD 需要人工审批。这是 DemoAI POC 业务规则，不是 PingPong 官方规则。

## Issuing Contract Status

当前只有 `IssuingProvider.create_vcc` 的 Mock 能力。公开 Issuing 页面和具体商户权限不足以让本 POC 安全确认完整 create/get/action/spending-control contract，因此没有编造 `PingPongIssuingAdapter` 字段，也没有将 Mock fixture 写成 `CONTRACT_VERIFIED`。

## Evidence

- `tests/test_poc.py::test_vcc_requires_human_approval_and_budget_gate`
- `tests/e2e/test_demo_flow.py::test_vcc_requires_approval_before_card_creation`
- `app/services/issuing_service.py`：Provider call 前做状态/RBAC检查
- `app/agents/finance_agent.py`：deterministic parser
- `app/integrations/llm/deepseek.py`：可选 DeepSeek JSON Parser；只做结构化提取

## Resume-safe claim

可以描述为：设计并实现带可选 LLM 意图解析的 VCC workflow，覆盖结构化申请、预算/RBAC、人工审批、Mock Issuing Adapter 和 Audit；LLM 仅负责自然语言解析，不应描述为自主发卡或真实 PingPong VCC Sandbox 联调。
