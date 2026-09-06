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
Mock / PingPong IssuingProvider
        ↓
AuditLog
```

Parser 只提取 `vendor`、`amount`、`currency`、`purpose`、`period_days`。缺失金额/币种时返回 `missing_fields`，不猜业务金额；金额、币种、预算、审批和当前状态由后端重新校验。LLM 输出使用 JSON mode 并经过 Pydantic 和 Decimal/币种/期限校验。

## Clarification and Scope UX

VCC 输入采用有边界的多轮澄清，而不是无限对话：

```text
接收输入 → 判断意图 → 补齐 vendor / amount / currency / purpose，并确认 period
→ 用户确认结构化参数 → Budget / RBAC / Approval → Human Confirmation → Create VCC
```

- `NEEDS_CLARIFICATION` 只展示已识别字段和缺失字段，不创建 `VCCApplication`，也不执行 Budget / Approval。
- 前端会保留本轮用户补充，并将用户消息合并后重新解析；最多由用户继续补充到字段完整。
- 空值不展示为 `UNKNOWN`、`0.00` 或业务默认值；状态显示为“未识别”“待补充”或“未执行”。
- 不属于 VCC 申请的请求返回 `OUT_OF_SCOPE`，明确支持范围和可用示例；绕过审批、修改安全规则或要求敏感卡数据时返回安全拒绝。
- 只有结构化申请完整且通过后端确定性校验后，才创建 Application。

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

当前已有 `MockPingPongIssuingAdapter` 和 `PingPongIssuingHttpAdapter`。HTTP Adapter 按官方公开 Issuing v2 Contract 实现 Create Card、Card Detail、Freeze/Unfreeze/Close、Spending Control、Dedicated Funds balance 和 Authorization logs，并通过 DTO/Mapper 丢弃 PAN/CVC。`card_product_code`、RSA/SM2 signer 和具体卡产品权限由 Sandbox 账户提供；因此当前状态是 `CONTRACT_VERIFIED + MOCK_VERIFIED + SANDBOX_PENDING`，不是 Sandbox Verified。

开卡调用还要求独立的 human confirmation。`POST /api/vcc/{application_id}/card` 是用户明确点击/调用的确认动作；Agent Parser、Budget Tool 和 Approval Service 都不能代替它。直接调用 `IssuingService.create_vcc(..., human_confirmed=False)` 会 fail closed。

## Evidence

- `tests/test_poc.py::test_vcc_requires_human_approval_and_budget_gate`
- `tests/e2e/test_demo_flow.py::test_vcc_requires_approval_before_card_creation`
- `app/services/issuing_service.py`：Provider call 前做状态/RBAC检查
- `app/agents/finance_agent.py`：deterministic parser
- `app/integrations/llm/deepseek.py`：可选 DeepSeek JSON Parser；只做结构化提取
- `tests/test_pingpong_unified_contract.py`：Issuing v2 request serialization、response parsing、error boundary 和敏感字段丢弃

## Resume-safe claim

可以描述为：设计并实现带可选 LLM 意图解析的 VCC workflow，覆盖结构化申请、预算/RBAC、人工审批、Mock Issuing Adapter 和 Audit；LLM 仅负责自然语言解析，不应描述为自主发卡或真实 PingPong VCC Sandbox 联调。
