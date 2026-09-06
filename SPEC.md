**# SPEC.md — AI Platform Global Payment Integration（PingPong FDE POC）**

\> 版本：v1.3

\> 状态：Ready for Implementation  

\> 语言：中文优先，关键技术名词保留英文  

\> 目标读者：本地 Coding Agent / 面试官 / FDE / 开发者

变更记录（v1.3，2026-09-06）：补充当前可读取的官方 Checkout V4 envelope/endpoint/signature 来源；将本地 Ledger 语义限定为事务边界内的 idempotent business effect；明确无官方 event ID 时使用 `delivery_fingerprint`；VCC 统一称为 `VCC Workflow Assistant`，支持 deterministic parser 和可选 LLM structured parser。

\---

**## 0. 文档定位**

本项目是一个 **\*\*面向 PingPong「AI 客户技术接入工程师（FDE）」岗位的求职作品集\*\***。

项目模拟一个真实可发生的客户交付场景：

\> 一家面向全球开发者提供模型 API 的 AI 平台，需要接入 PingPong Checkout，为海外开发者提供 Credits 充值能力；同时企业自身存在 AWS / Google Cloud / SaaS 等海外支出，希望探索通过 PingPong VCC + Agent 将「付款申请 → 审批 → 开卡 → 用卡 → 对账」流程自动化。

项目不是 PingPong 官方项目，也不得暗示真实服务过 PingPong 客户。

README 必须明确声明：

\> 本项目为求职作品集，基于 PingPong 官方公开 API、公开产品能力与典型客户接入场景构建，不代表 PingPong 官方实施项目或真实客户案例。

\---

**# 1. 项目目标**

本项目不以“功能数量”为目标，而以证明以下 FDE 能力为目标：

1\. 能从客户业务需求出发完成 API 接入方案设计。

2\. 理解跨境收单核心 API 链路：Create Payment、Query、Webhook、Refund。

3\. 理解支付系统关键工程问题：

   \- Idempotency

   \- Webhook 去重

   \- 支付状态机

   \- 主动查单

   \- 最终一致性

   \- Retry / Timeout / 429

   \- Trace / Audit

4\. 能使用 Python / FastAPI 快速完成可运行 POC。

5\. 能通过 Adapter 隔离第三方支付 API。

6\. 能设计 Agent + Tool + Approval + Audit 的 VCC 用卡流程。

7\. 能输出客户可阅读的 Developer Guide、Troubleshooting Guide、Go-live Checklist。

8\. 项目能够通过明确测试用例进行人工和自动验收。

\---

**# 2. 成功标准**

项目完成后，面试展示时必须可以在 10\~15 分钟内演示以下完整路径：

\`\`\`text

开发者充值 100 USD Credits

        ↓

创建本地订单

        ↓

调用 PingPong Checkout Adapter

        ↓

支付进入 PROCESSING

        ↓

Webhook / 模拟 Webhook

        ↓

支付 SUCCESS

        ↓

Credits +100

        ↓

后台可查看支付状态、请求 ID、交易 ID 和事件日志

        ↓

发起退款

        ↓

退款完成 / 模拟完成

\`\`\`

以及第二条路径：

\`\`\`text

财务人员输入：

“为 AWS 9 月账单申请一张 20,000 USD 虚拟卡”

        ↓

Agent 结构化解析

        ↓

Budget Tool 检查

        ↓

Approval

        ↓

Human Confirm

        ↓

VCC Tool

        ↓

PingPong Issuing Adapter / Mock Adapter

        ↓

生成虚拟卡记录

        ↓

Audit Log

\`\`\`

\---

**# 3. 范围定义**

**## 3.1 P0 — 必须实现**

**### A. AI Credits 收单闭环**

\- 创建充值订单

\- 创建 Payment

\- 查询 Payment

\- 接收 Checkout Webhook

\- Checkout Webhook 验签（Mock 与 Sandbox 均须覆盖）

\- Webhook 幂等 / 去重

\- 支付状态机

\- Credits 入账

\- 主动查单补偿

\- 创建退款

\- 查询退款

\- 基础对账视图

\- Trace ID / Request ID / Transaction ID

\- Sandbox-first Checkout Adapter 与确定性 Mock Adapter

\- 统一客户支付动作（next\_action），不得假定固定 checkout\_url 字段

**### B. FDE 交付文档**

必须包含：

\- Customer Scenario

\- Requirement Analysis

\- Solution Design

\- API Integration Guide

\- Payment State Machine

\- Webhook Design

\- Troubleshooting Guide

\- Test Plan

\- Go-live Checklist

**### C. 自动化测试**

至少覆盖：

\- 幂等

\- Webhook 重复通知

\- Webhook 延迟

\- 主动查单恢复

\- 支付失败

\- 退款

\- 重复退款

\- PingPong timeout

\- PingPong 429

\- 无效 Webhook 签名

\- 并发 Webhook / 查单入账

\- 幂等键 payload 冲突

\- 鉴权与 RBAC 越权

\- Webhook / 日志敏感字段脱敏

**### Sandbox-first 交付策略**

\- Checkout 的实现顺序为：Sandbox Adapter / 鉴权与协议映射 → Mock Adapter → 业务闭环。

\- Sandbox 是首要真实集成路径；Mock 仅用于确定性自动化测试、无凭证本地运行和异常场景演示。

\- 不得静默从 Sandbox 降级到 Mock。运行模式必须由 PINGPONG\_MODE 显式指定。

\- 真实 Sandbox 验证的外部前置条件是：合法测试账户与凭证、已开通的 Checkout 产品/支付方式、可公网访问的 HTTPS callback，以及已确认的客户支付动作契约。

\- 未具备上述前置条件时，交付状态只能写为 Mock Verified / Sandbox Pending；不得声称已完成 Sandbox 联调。

\---

**## 3.2 P1 — 应实现**

**### VCC Finance Agent**

实现 Agent 化的企业用卡流程：

\`\`\`text

用户自然语言申请

→ 结构化付款需求

→ Budget Check

→ Approval Policy

→ Human Confirmation

→ Create VCC Tool

→ PingPong Issuing Adapter / Mock

→ Audit

\`\`\`

P1 默认允许使用 Mock Issuing Adapter。

如果拥有真实 PingPong Issuing Sandbox 权限，可切换为 Sandbox Adapter。

禁止在没有真实联调的情况下在 README 中声称“完成 PingPong VCC Sandbox 联调”。

\---

**## 3.3 P2 — 本版本不实现**

以下能力明确 Deferred，避免过度设计：

\- Stripe / Adyen 等真实多供应商接入

\- 智能支付路由

\- 真实 KYC / KYB

\- 真实清结算

\- 真实银行卡敏感信息存储

\- 真实 PCI DSS 场景

\- 复杂 FX

\- Chargeback / Dispute 完整流程

\- 多租户 SaaS 平台

\- 大规模高并发压测平台

\- LLM 多 Agent 系统

P2 可以在 README Roadmap 中体现，但不得影响 P0 交付。

\---

**# 4. 真实业务场景**

**## 4.1 客户画像**

虚构客户名：\`DemoAI\`

业务：模型 API 聚合 / AI API 平台。

客户用户：全球开发者与中小企业。

商业模式：

1\. Credits 预充值

2\. 月度订阅（暂不实现自动续费）

主要市场：

\- US

\- Singapore

\- Hong Kong

\- EU

主要币种：

\- USD

\- SGD

\- HKD

\- EUR

POC 首期仅真正实现 USD。

Credits 定价规则固定为：1.00 USD = 1.00 USD\_CREDIT。该规则仅适用于本 POC；未来引入多币种或浮动汇率时，必须新增报价与汇率快照机制。

\---

**## 4.2 客户痛点**

**### 收入侧**

\- 希望通过统一支付 API 接收海外用户付款。

\- 不能把前端 redirect 当成支付最终结果。

\- Webhook 可能丢失、重复、乱序。

\- 用户重复点击充值不能产生重复 Credits。

\- 支付状态与本地订单状态需要保持一致。

\- 出现问题时必须能快速通过 request\_id / transaction\_id 排查。

**### 支出侧**

客户每月存在：

\- AWS

\- Google Cloud

\- Datadog

\- GitHub

\- 广告平台

\- 海外 SaaS

传统用卡流程人工步骤多，拟通过 VCC + Agent 优化。

\---

**# 5. 用户角色**

**## 5.1 Developer**

能够：

\- 查看 Credits

\- 创建充值订单

\- 发起支付

\- 查看支付结果

**## 5.2 Finance User**

能够：

\- 查看交易

\- 发起退款

\- 发起 VCC 用卡申请

\- 查看审批与用卡状态

**## 5.3 Approver**

能够：

\- 查看 VCC 申请

\- Approve / Reject

**## 5.4 FDE / Admin**

能够：

\- 查看 PingPong API 调用日志

\- 查看 Webhook Event

\- 查看失败订单

\- 手动触发主动查单

\- 查看 Trace

\- 查看对账异常

**## 5.5 Identity 与 RBAC**

所有受保护 API 都必须从已认证 Principal 获取 actor\_id 和 role，禁止信任客户端在请求体、Query 或 Header 中自报的 user\_id / role。

\| 操作 | 最低角色 | 授权范围 |

\|---|---|---|

\| 创建充值、查看余额和支付 | Developer | 仅本人资源 |

\| 查看交易、发起退款、发起 VCC 申请 | Finance User | 全局财务资源 |

\| 审批 / 拒绝 VCC | Approver | 被授权的申请 |

\| 对账、查看 Debug / Webhook / Provider Call | FDE / Admin | 全局运维资源 |

P0 可实现只用于本地演示的认证方式，但必须通过依赖注入隔离，并在 README 中声明其不适用于生产。不得通过可伪造的角色 Header 实现授权。

\---

**# 6. 核心业务流程**

**# 6.1 Credits 充值**

\`\`\`text

Developer

  ↓

POST /api/topups

  ↓

Create Local Order

  ↓

PaymentService.create\_payment()

  ↓

PingPongCheckoutAdapter.create\_payment()

  ↓

PingPong Sandbox / Mock

  ↓

返回 payment data

  ↓

PaymentStateMachine.apply\_provider\_observation(...)

  ↓

PENDING → PROCESSING

SUCCESS → SUCCEEDED + Credit Ledger（原子且幂等）

AUTH\_SUCCESS → REVIEW\_REQUIRED

FAIL → FAILED

CLOSE → CANCELLED

\`\`\`

Create Payment 的**已认证服务端响应**属于可信 Provider Observation；前端 redirect / callback 页面不属于可信支付终态依据。

Credits 只能在可信服务端观察到 Provider `SUCCESS` 后增加。可信观察来源统一限定为：

\- 已认证的 Create Payment Response

\- 已验签的 Checkout Webhook

\- 已认证的 Query Payment / Reconciliation Response

以上三种来源必须调用同一个 Payment State Machine Service。任何来源观察到 `SUCCESS` 时，都只能通过统一状态迁移逻辑原子写入 TOPUP CreditLedger；CreditLedger 的数据库唯一约束是防止重复入账的最终防线。

因此，不得编写“Create Payment 返回后直接改余额”的旁路逻辑；如果 Create Payment Response 已明确返回 `SUCCESS`，应通过 State Machine 将 Payment 迁移为 `SUCCEEDED` 并原子入账一次。若返回 `PENDING`，则保持 `PROCESSING`，等待 Webhook 或主动 Query / Reconciliation 确认终态。

Topup 必须携带 Idempotency-Key Header。服务端在一个本地数据库事务中创建 API 幂等记录、PaymentOrder、partner\_transaction\_id 和 provider\_request\_id；随后在事务外调用 Provider。

接口从已认证 Developer 取得用户身份，不接收 user\_id。Provider 返回的客户后续动作统一映射为 next\_action（例如 REDIRECT、QR\_CODE 或 NONE）；next\_action URL 只在响应中短暂返回，不写入日志或持久化记录。

\---

**# 6.2 Webhook 入账**

\`\`\`text

PingPong

  ↓

POST /api/webhooks/pingpong/checkout

  ↓

Verify

  ↓

Event Deduplication

  ↓

Lookup Payment

  ↓

Validate State Transition

  ↓

Update Payment

  ↓

Credit Ledger +100

  ↓

Webhook Event = PROCESSED

\`\`\`

必须保证：

\> 同一笔 SUCCESS Webhook 即使发送 10 次，Credits 只增加一次。

验签、订单匹配、状态迁移、WebhookEvent 写入、CreditLedger 写入与余额快照更新必须由同一个事务边界保护。Provider 调用不包含在该事务中。

\---

**# 6.3 主动查单**

Webhook 不作为唯一一致性保障。

后台任务：

\`\`\`text

Payment = PROCESSING

AND updated\_at < threshold

        ↓

Query PingPong Payment

        ↓

SUCCESS / FAIL / CLOSE

        ↓

更新本地状态

        ↓

必要时执行 Credits Ledger

\`\`\`

同时提供人工触发：

\`POST /api/admin/payments/{id}/reconcile\`

超时或连接失败时，Payment 保持 PROCESSING，并设置 next\_reconcile\_at；不得新建 Payment 或使用新的 provider\_request\_id 重试创建。

P0 默认在 Payment 进入 PROCESSING 后 1 小时开始查单；开发演示可由配置缩短。扫描任务每次最多处理 20 条到期记录，必须复用通用限流与 Retry Policy。SQLite 模式仅支持单应用实例运行该后台扫描。

\---

**# 6.4 Refund**

\`\`\`text

Finance

 ↓

POST /api/refunds

 ↓

检查原 Payment = SUCCESS

 ↓

检查可用 Credits

 ↓

创建 RefundOrder + CreditHold

 ↓

生成 partner\_refund\_id / provider\_request\_id

 ↓

PingPongCheckoutAdapter.create\_refund()

 ↓

RefundOrder = PROCESSING

 ↓

Webhook / Query Refund

 ↓

RefundOrder = SUCCEEDED（UI 显示 REFUNDED）

\`\`\`

POC 简化规则：

\- P0 可以只实现全额退款。

\- 数据模型应允许未来扩展部分退款。

Credits 回退策略：

\- 退款请求首先检查可用 Credits（已记账余额减去未结算 Hold）。

\- 可用 Credits 足够时，在本地事务内创建 CreditHold，冻结对应 Credits；随后才可调用 Provider 退款。

\- Provider 退款成功时，写入负向 REFUND\_REVERSAL Ledger 并结算 Hold；Provider 退款失败时释放 Hold。

\- 如果 Credits 不足：RefundOrder 进入 \`MANUAL\_REVIEW\`，**\*\*不得调用 Provider 退款 API\*\***，也不得产生负余额。

该规则属于 DemoAI 业务规则，不是 PingPong 官方规则。

\---

**# 7. 支付与退款状态机**

本地状态不得完全复制第三方状态，应建立 Domain State。Payment 与 RefundOrder 是独立聚合；退款不得改变 Payment 的成功事实。

\`\`\`text

CREATED

  ↓

PROCESSING

  ├── SUCCEEDED

  ├── FAILED

  ├── CANCELLED

  └── REVIEW\_REQUIRED

\`\`\`

\| Provider 状态 | Payment Domain State | Credits 行为 |

\|---|---|---|

\| PENDING | PROCESSING | 不入账 |

\| SUCCESS | SUCCEEDED | 原子入账一次 |

\| FAIL | FAILED | 不入账 |

\| CLOSE | CANCELLED | 不入账 |

\| AUTH\_SUCCESS | REVIEW\_REQUIRED | 不入账，等待人工处理 |

P0 固定 manual\_capture=false，不实现 Capture。AUTH\_SUCCESS 属于异常保护路径，不能作为 Credits 发放依据。

Provider 状态观察来源可以是 Create Payment Response、已验签 Webhook 或 Query / Reconciliation Response。三种来源必须统一进入同一 State Machine Service，不允许分别实现终态处理或 Credits 入账逻辑。前端 redirect / callback 页面不属于 Provider Observation，不能驱动支付终态或 Credits 入账。

RefundOrder：

\`\`\`text

CREATED → PROCESSING → SUCCEEDED | FAILED

                       └→ MANUAL\_REVIEW

\`\`\`

P0 只支持全额退款，因此一个 PaymentOrder 最多关联一个 RefundOrder。Payment 退款后仍为 SUCCEEDED；是否已退款由成功的 RefundOrder 派生，UI 可展示为 REFUNDED。

允许状态转移必须集中定义。

禁止业务代码中散落：

\`\`\`python

payment.status = "SUCCESS"

\`\`\`

必须通过：

\`\`\`python

payment.transition\_to(...)

\`\`\`

或者统一 State Machine Service。

\---

**# 8. PingPong API 接入约束**

**## 8.1 Checkout V4**

优先参考当前 PingPong 官方 Checkout V4 文档。

本次复核的可读取官方 Checkout V4 developer guide 当前公开接口包括：

\`\`\`text

POST /v4/payment/prePay

POST /v4/payment/query

POST /v4/payment/refund

POST /v4/payment/getRefund

\`\`\`

说明：Prompt 初始资料中的 `/api/acq/v4/...` 路径未能从当前可读取的公开页面取得完整契约；本项目不将两套路径混写，具体证据与未确认项见 `docs/adr/ADR-001-pingpong-checkout-v4-contract.md`。

官方文档导航还列出 Create Session，但在未取得 Sandbox 测试账户和已开通产品的精确契约前，不得假定其 endpoint、字段或返回 URL。

本项目 P0 使用：

\- create payment

\- query payment

\- create refund

\- query refund

\- checkout webhook

Create Payment 应使用：

\- \`partner\_transaction\_id\`：DemoAI 商户订单业务 ID

\- \`request\_id\`：请求幂等 ID

本 POC 使用 Hosted `prePay`。客户后续操作应读取官方响应中的 `paymentUrl` 并映射为本地 `next_action=REDIRECT`；不得假定响应一定含 `checkout_url`。API-only `unifiedPay` 是独立的卡数据/PCI 路径，不属于本 POC。

P0 不得向 PingPong 发送 PAN、CVV 或由本 POC 收集的卡信息。payment\_method 的可用取值、客户动作和 Sandbox 测试数据必须以已开通产品的官方资料为准。

不得自己假定任何未从官方文档确认的 PingPong 字段格式。

Coding Agent 在实现 Sandbox Adapter 前必须重新核对当前官方文档。

\---

**## 8.2 环境**

系统支持：

\`\`\`env

PINGPONG\_MODE=mock|sandbox

\`\`\`

PINGPONG\_MODE 必须显式配置，禁止自动 fallback。Sandbox 模式启动时必须校验对应的 base URL、`accId`、`clientId`、salt、Hosted 支付结果/取消地址、HTTPS notify URL 和 shopper IP；缺失任一必需项必须 fail fast，且错误信息不得包含 Secret。

**### mock**

确定性本地测试与无凭证演示模式。

特点：

\- 无外部凭证也可完整跑通。

\- 可模拟 SUCCESS / FAIL / TIMEOUT / 429。

\- 可人工触发 Webhook。

**### sandbox**

当用户提供合法 Sandbox Credential 后启用。

Sandbox Adapter 是首要实现路径，但只有在测试账户、产品权限、支付方式和 callback 已就绪后才能进行真实调用验证。

所有 Secret 只能通过环境变量加载。

禁止：

\- 写入 Git

\- 打印完整 Secret

\- 写入测试快照

\---

**## 8.3 Authentication**

PingPong 不同开放产品 / API 版本可能存在不同认证约定。

Adapter 必须按照对应官方文档实现：

\- Authorization

\- sign

\- sign-version

\- 或其他当前版本要求

禁止凭经验编造签名算法。

\`PingPongAuthProvider\` 必须与业务 Adapter 分离。

\`\`\`text

PaymentService

    ↓

PingPongCheckoutAdapter

    ↓

PingPongAuthProvider

\`\`\`

\---

**## 8.4 Rate Limit**

PingPong 开放平台公开接入指南存在每 appId 20 QPS、超限返回 429 的说明。

由于不同产品可能存在不同限制，本项目不得把 20 QPS 当作所有 Checkout API 的永久固定 SLA。

客户端必须具备通用 429 处理：

\- exponential backoff

\- jitter

\- retry limit

\- metric / log

\---

**# 9. PCI / 敏感信息约束**

这是项目强制安全要求。

本项目：

\- 不采集真实 PAN

\- 不存储 CVV

\- 不打印卡号

\- 不要求用户输入真实银行卡数据

\- 不将真实支付凭证提交到 GitHub

优先使用：

\- PingPong Hosted / Sandbox 页面

\- 官方 Sandbox 测试数据

\- Mock Payment Provider

如果某种 Direct API 集成涉及 PCI 要求，本 POC 不实现敏感卡数据处理。

Webhook 原始 Body 只能在请求内存中用于验签，验签后立即丢弃；不得将完整 payload、token\_value、签名、姓名、邮箱、电话、IP 或支付动作 URL 写入数据库、日志、测试快照或 Audit。

README 中应明确说明该设计决定。

\---

**# 10. 系统架构**

目标：简单、清晰、可解释，不做微服务拆分。

\`\`\`text

┌──────────────────────────┐

│ Web UI                   │

│ Developer / Finance      │

└─────────────┬────────────┘

              │

              ▼

┌──────────────────────────┐

│ FastAPI Application      │

│                          │

│ API Layer                │

│     ↓                    │

│ Application Services     │

│     ↓                    │

│ Domain                   │

│     ↓                    │

│ Provider Adapters        │

└─────────────┬────────────┘

              │

       ┌──────┴──────┐

       ▼             ▼

 PingPong Mock   PingPong Sandbox

\`\`\`

VCC Workflow Assistant（当前实现为 deterministic fallback + 可选 LLM structured parser；不宣称自主 LLM Agent）：

\`\`\`text

Finance User

    ↓

Finance Agent

    ↓ Structured Output

VCCApplication

    ↓

Budget Tool

    ↓

Approval Service

    ↓

Human Confirm

    ↓

CreateVCCTool

    ↓

Issuing Service

    ↓

PingPongIssuingAdapter

\`\`\`

\---

**# 11. 推荐技术栈**

**## Backend**

\- Python 3.12+

\- FastAPI

\- Pydantic v2

\- SQLAlchemy 2.x

\- Alembic

\- httpx

\- pytest

**## Database**

本地默认：

\- SQLite

可选：

\- PostgreSQL via Docker Compose

禁止为了“企业级”强制引入 Kafka / Redis / Kubernetes。

只有出现明确需求后再增加。

**## Agent**

优先：

\- LangGraph 或轻量自定义 Workflow

\- Structured Output

\- Tool Calling

如果不用 LangGraph 能更简单完成需求，可以不用。

Agent 只负责：

\- 意图理解

\- 结构化参数提取

\- 决策建议

\- 工具编排

Agent 不负责：

\- 权限

\- 额度强校验

\- 幂等

\- 审批最终结果

\- Audit

\- 第三方 API Secret

\---

**# 12. 代码结构**

推荐：

\`\`\`text

pingpong-ai-fde-poc/

├── README.md

├── SPEC.md

├── AGENTS.md

├── .env.example

├── docker-compose.yml

├── pyproject.toml

│

├── app/

│   ├── main.py

│   ├── api/

│   │   ├── topups.py

│   │   ├── payments.py

│   │   ├── refunds.py

│   │   ├── webhooks.py

│   │   ├── reconciliation.py

│   │   └── vcc.py

│   │

│   ├── domain/

│   │   ├── payment.py

│   │   ├── refund.py

│   │   ├── credit.py

│   │   └── vcc.py

│   │

│   ├── services/

│   │   ├── payment\_service.py

│   │   ├── refund\_service.py

│   │   ├── credit\_service.py

│   │   ├── reconciliation\_service.py

│   │   ├── approval\_service.py

│   │   └── issuing\_service.py

│   │

│   ├── integrations/

│   │   └── pingpong/

│   │       ├── base.py

│   │       ├── auth.py

│   │       ├── checkout.py

│   │       ├── issuing.py

│   │       ├── mock\_checkout.py

│   │       └── mock\_issuing.py

│   │

│   ├── agents/

│   │   ├── finance\_agent.py

│   │   ├── schemas.py

│   │   └── tools.py

│   │

│   ├── models/

│   ├── repositories/

│   ├── observability/

│   └── config.py

│

├── tests/

│   ├── unit/

│   ├── integration/

│   └── e2e/

│

├── docs/

│   ├── 01-customer-scenario.md

│   ├── 02-requirement-analysis.md

│   ├── 03-solution-design.md

│   ├── 04-api-integration-guide.md

│   ├── 05-payment-state-machine.md

│   ├── 06-webhook-design.md

│   ├── 07-vcc-agent-design.md

│   ├── 08-troubleshooting.md

│   ├── 09-test-plan.md

│   └── 10-go-live-checklist.md

│

└── scripts/

    ├── simulate\_webhook.py

    └── demo.sh

\`\`\`

\---

**# 13. 数据模型**

**## 13.1 User**

\`\`\`text

id

email

role

created\_at

\`\`\`

\---

**## 13.2 CreditAccount**

\`\`\`text

id

user\_id

credit\_unit              USD\_CREDIT

posted\_balance           已结算余额快照

available\_balance        可用余额快照（扣除有效 Hold）

updated\_at

\`\`\`

Credits 使用 Decimal，不允许 float。P0 的 CreditAccount 不使用法币 currency 字段。

\---

**## 13.3 CreditLedger**

必须用 Ledger，而不是只修改余额。

\`\`\`text

id

account\_id

entry\_type           TOPUP / REFUND\_REVERSAL / ADJUSTMENT

credit\_amount        带符号的 Credits 数额

fiat\_amount

fiat\_currency

pricing\_rule\_version P0\_USD\_1\_TO\_1

reference\_type

reference\_id

idempotency\_key

created\_at

\`\`\`

Ledger 只追加，不更新历史记录。idempotency\_key 唯一；(reference\_type, reference\_id, entry\_type) 也必须唯一。余额快照只能在与 Ledger 写入相同的事务中更新。

\---

**## 13.4 CreditHold**

\`\`\`text

id

account\_id

refund\_id

credit\_amount

status               HELD / SETTLED / RELEASED

created\_at

settled\_at

released\_at

\`\`\`

refund\_id 唯一。可用 Credits = 已结算余额 - HELD 金额。Hold 只在退款成功时结算为 REFUND\_REVERSAL Ledger，在退款失败时释放。

\---

**## 13.5 ApiIdempotency**

\`\`\`text

id

actor\_id

method

canonical\_route

key\_hash

request\_hash

resource\_type

resource\_id

status               IN\_PROGRESS / COMPLETED

created\_at

completed\_at

\`\`\`

Unique：(actor\_id, method, canonical\_route, key\_hash)。

相同幂等键且 request\_hash 一致时返回首次创建的资源；request\_hash 不一致时返回 409 Conflict。对于 PROCESSING Payment，如需恢复未持久化的 next\_action，允许以相同 provider\_request\_id 和 partner\_transaction\_id 安全重放 Provider Create Payment，以获得其幂等缓存响应；不得持久化含支付动作 URL 的完整响应。

\---

**## 13.6 PaymentOrder**

\`\`\`text

id

user\_id

partner\_transaction\_id

provider\_request\_id

amount

currency

status

provider

provider\_transaction\_id

provider\_status

failure\_code

failure\_message

next\_reconcile\_at

reconcile\_attempts

created\_at

updated\_at

\`\`\`

Unique：

\- (provider, partner\_transaction\_id)

\- (provider, provider\_transaction\_id)，provider\_transaction\_id 非空时

\- (provider, partner\_transaction\_id, provider\_request\_id)，与 Provider 幂等语义一致

\---

**## 13.7 RefundOrder**

\`\`\`text

id

payment\_id

partner\_refund\_id

provider\_request\_id

amount

currency

status

provider\_refund\_id

provider\_status

credit\_hold\_id

created\_at

updated\_at

\`\`\`

P0 的 Unique：(payment\_id)、partner\_refund\_id、provider\_refund\_id（非空时）。status 使用 CREATED / PROCESSING / SUCCEEDED / FAILED / MANUAL\_REVIEW。

\---

**## 13.8 WebhookEvent**

\`\`\`text

id

provider

event\_type

event\_key

resource\_id

provider\_status

amount

currency

payload\_hash

delivery\_id             仅用于观测，不作业务幂等

status                  RECEIVED / PROCESSED / IGNORED / REJECTED / FAILED

error

received\_at

processed\_at

\`\`\`

\`event\_key\` 必须唯一。支付事件使用 checkout.payment:{transaction\_id}:{status}；退款事件使用 checkout.refund:{refund\_id}:{status}。若缺少 Provider ID，才可使用经验证的商户业务 ID 作为降级键。

不得依赖“Webhook 每次一定有唯一 event\_id”的假设，也不得使用 delivery\_id / msg\_id 作为业务幂等条件。payload\_hash 仅用于诊断，不能替代业务唯一键。

不保存原始 payload，只保存上述 allowlist 字段和 payload\_hash。

\---

**## 13.9 ProviderCallLog**

\`\`\`text

id

provider

operation

trace\_id

provider\_request\_id

http\_status

provider\_code

latency\_ms

success

error\_type

created\_at

\`\`\`

不得记录 Secret、CVV、完整卡号等敏感字段。

请求 / 响应 Body、Authorization、sign、token\_value、支付动作 URL、姓名、邮箱、电话和 IP 均不得写入 ProviderCallLog。

\---

**## 13.10 AuditLog**

\`\`\`text

id

actor\_id

actor\_role

action

resource\_type

resource\_id

trace\_id

outcome

created\_at

\`\`\`

AuditLog 用于记录授权后的业务动作与结果，不得记录请求 / 响应 Body、Secret、PII 或支付动作 URL。

\---

**## 13.11 VCCApplication**

\`\`\`text

id

requester\_id

vendor

purpose

amount

currency

period

status

approval\_status

provider\_card\_id

masked\_card

created\_at

updated\_at

\`\`\`

状态：

\`\`\`text

DRAFT

→ PENDING\_APPROVAL

→ APPROVED

→ CARD\_CREATING

→ ACTIVE

→ CLOSED

或

→ REJECTED

→ FAILED

\`\`\`

\---

**# 14. API 设计**

除 Webhook 外，所有 API 都必须通过认证依赖取得 Principal。所有写操作都必须写入 actor\_id、actor\_role、trace\_id 到 Audit；不得由客户端指定 user\_id 或 role。

**## 14.1 Topup**

**### POST /api/topups**

Required Header：

\`\`\`text

Idempotency-Key: \<client generated key>

\`\`\`

Request：

\`\`\`json

{

  "amount": "100.00",

  "currency": "USD"

}

\`\`\`

Response：

\`\`\`json

{

  "payment\_id": "payment\_xxx",

  "payment\_status": "PROCESSING",

  "next\_action": {

    "type": "REDIRECT",

    "url": "..."

  }

}

\`\`\`

next\_action 可以为 REDIRECT、QR\_CODE 或 NONE。URL 属于一次性客户动作，只允许直接返回给调用方，不得存储或记录日志。同一 Idempotency-Key 与相同请求体返回同一 Payment；同一键不同请求体返回 409。

\---

**## 14.2 Query Payment**

**### GET /api/payments/{payment\_id}**

返回：

\- local status

\- provider status

\- provider transaction id

\- amount

\- currency

\- timestamps

\---

**## 14.3 Webhook**

**### POST /api/webhooks/pingpong/checkout**

要求：

1\. 原始 Body 可用于验签。

2\. 验签失败返回 401 / 400。

3\. 验签成功后，将请求解析为严格的 allowlist 模型；兼容官方字段可能出现的 requestId / request\_id 命名差异。

4\. 重复 Event 不重复执行业务逻辑。

5\. 有效且已处理、已忽略或已拒绝的通知均按当前 Checkout 官方约定返回确认体；当前通用约定为 {"code":200,"message":"SUCCESS"}。

6\. 有效但未知订单、金额/币种不匹配时，记录 REJECTED 安全事件、不入账，并返回确认体，避免无意义的无限重试。

7\. 临时数据库故障返回 5xx，以便 Provider 重试。

8\. Handler 只做必要工作；可选 LLM 调用必须有明确 timeout，失败时进入 `NEEDS_CLARIFICATION`，不得阻塞或改变资金流程。

Mock 模式允许：

\`X-Mock-Signature\`。

Sandbox 模式必须按照 PingPong 官方当前 Webhook 验签规则实现。

\---

**## 14.4 Refund**

**### POST /api/refunds**

Required Header：

\`\`\`text

Idempotency-Key: \<client generated key>

\`\`\`

\`\`\`json

{

  "payment\_id": "payment\_xxx"

}

\`\`\`

仅 Finance User 可调用。P0 只支持全额退款；若 Credits 不足，返回对应的 RefundOrder，状态为 MANUAL\_REVIEW，且绝不触发 Provider 调用。

\---

**## 14.5 Reconciliation**

**### POST /api/admin/payments/{payment\_id}/reconcile**

行为：

\- 仅 FDE / Admin 可调用

\- 主动 Query Provider

\- 比较本地状态

\- 必要时修复

\- 写 Audit / ProviderCallLog

\---

**## 14.6 VCC Workflow Assistant（原需求称 VCC Agent）**

**### POST /api/vcc/agent**

Input：

\`\`\`json

{

  "message": "为 AWS 9 月账单申请一张 20000 USD 的虚拟卡，有效期 30 天"

}

\`\`\`

Structured Output：

\`\`\`json

{

  "vendor": "AWS",

  "amount": "20000.00",

  "currency": "USD",

  "purpose": "cloud\_service",

  "period\_days": 30,

  "missing\_fields": []

}

\`\`\`

Agent 不得直接创建卡。

必须：

\`\`\`text

Agent Parse

→ Business Validation

→ Budget Check

→ Approval

→ Human Confirm

→ Tool Execution

\`\`\`

\---

**# 15. Adapter 设计**

定义协议：

\`\`\`python

class CheckoutProvider(Protocol):

    async def create\_payment(...): ...

    async def query\_payment(...): ...

    async def create\_refund(...): ...

    async def query\_refund(...): ...

\`\`\`

create\_payment 的输入只接受业务订单、法币金额、币种、商户用户标识、redirect\_url / notify\_url 和已确认的非敏感支付方式信息；不得接受 PAN、CVV 或前端原始卡信息。

create\_payment 返回统一的 ProviderPaymentResult：

\`\`\`text

provider\_transaction\_id

provider\_request\_id

provider\_status

next\_action.type        REDIRECT / QR\_CODE / NONE

next\_action.url         仅内存中返回给调用方，不持久化

next\_action.qr\_payload  仅内存中返回给调用方，不持久化

\`\`\`

实现：

\`\`\`text

MockPingPongCheckoutAdapter

PingPongSandboxCheckoutAdapter

\`\`\`

Business Service 不允许：

\`\`\`python

if pingpong:

    ...

\`\`\`

业务层只能依赖接口。

Sandbox Adapter 负责将当前官方 Checkout V4 的字段、鉴权和状态映射为上述协议；Mock Adapter 必须模拟同一协议，而不是定义另一套业务语义。

同样：

\`\`\`python

class IssuingProvider(Protocol): ...

\`\`\`

\---

**# 16. Retry / Timeout / 错误处理**

**## 16.1 Timeout**

httpx 必须显式配置：

\- connect timeout

\- read timeout

\- total / pool timeout（按实现能力）

不得无 timeout 调第三方 API。

\---

**## 16.2 Retry**

只对可安全重试的操作自动重试。

Create Payment 能否重试依赖幂等键。

当 Create Payment 出现 timeout 或 connection error，必须保留既有 provider\_request\_id 和 partner\_transaction\_id，标记 Payment 为 PROCESSING 并优先 Query / Reconcile；禁止用新 ID 盲目创建第二笔支付。

要求：

\`\`\`text

Retryable:

\- timeout

\- connection error

\- 429

\- selected 5xx

Non-Retryable:

\- parameter error

\- auth/sign error

\- known business rejection

\`\`\`

指数退避：

\`\`\`text

base \* 2^attempt + jitter

\`\`\`

测试不依赖真实 sleep；Retry Policy 必须可注入 / 可 mock。

\---

**# 17. Webhook 幂等与乱序**

必须显式处理：

Create Payment Response、Webhook 与主动查单必须调用同一 State Machine Service。对任一可信 Provider Observation 的 SUCCESS 处理，都必须以 CreditLedger 的数据库唯一约束为最终防线，而不是只依赖应用内 if 判断。Create Payment 已观察到 SUCCESS 后，后续重复 SUCCESS Webhook 或 Query 不得重复入账。

**## Case A**

SUCCESS 收到两次。

预期：

\- Payment 仍为 SUCCEEDED

\- Credits 只增加一次

**## Case B**

SUCCESS 后又收到 PENDING。

预期：

\- 不允许状态倒退

\- Event 标记 IGNORED

**## Case C**

Webhook 没收到。

预期：

\- 主动查单后恢复 SUCCEEDED

\- Credits 正确增加

**## Case D**

未知订单 Webhook。

预期：

\- 不创建虚假订单

\- 记录 REJECTED 安全事件（不保存原始 payload）

\- 不入账

\- 对已验签且确定无法处理的事件返回官方确认体；对暂时性内部错误返回 5xx

**## Case E**

同一 Idempotency-Key 发送不同金额或币种。

预期：

\- 返回 409 Conflict

\- 不创建 Payment / Refund

\- 不调用 Provider

**## Case F**

10 个并发 SUCCESS Webhook 与一次主动查单同时到达。

预期：

\- Payment 最终为 SUCCEEDED

\- 仅存在一条 TOPUP Ledger

\- 余额只增加一次

\---

**# 18. 对账设计**

P0 只实现“交易状态一致性对账”，不实现银行级资金清算。

Reconciliation Result：

\`\`\`text

MATCHED

LOCAL\_STALE

PROVIDER\_NOT\_FOUND

AMOUNT\_MISMATCH

CURRENCY\_MISMATCH

MANUAL\_REVIEW

\`\`\`

后台展示：

\| Local Order | Local | Provider | Amount | Result |

\|---|---|---|---|---|

\| A001 | PROCESSING | SUCCESS | 100 USD | LOCAL\_STALE |

允许人工执行：

\`Reconcile\`。

\---

**# 19. VCC Workflow Assistant 业务规则**

POC 规则，不代表 PingPong 官方风控规则。

**## 19.1 Budget**

Mock Budget：

\`\`\`text

Cloud Monthly Budget = 50,000 USD

Used = 10,000 USD

\`\`\`

申请 20,000 USD → PASS。

申请 60,000 USD → REJECT。

\---

**## 19.2 Approval**

\`\`\`text

<= 1,000 USD

→ 可简化审批

\> 1,000 USD

→ 必须 Human Approval

\`\`\`

即便 Agent 高置信，也不能绕过 Approval。

\---

**## 19.3 VCC Tool**

Tool Schema：

\`\`\`text

create\_vcc(

  application\_id,

  vendor,

  amount,

  currency,

  period\_days

)

\`\`\`

Tool 内部：

1\. 检查 application = APPROVED

2\. 检查 RBAC

3\. 检查幂等

4\. 调 Issuing Adapter

5\. 保存 masked card / provider card id

6\. 写 Audit

LLM 不获得 Provider Secret。

\---

**# 20. UI 要求**

UI 不是项目重点，保持最小化。

允许：

\- FastAPI + Jinja/HTMX

\- 简单 React / Next.js

\- Streamlit（如果不会妨碍架构展示）

推荐提供 4 个页面：

**## Developer Console**

\- Credits balance

\- Topup

\- Payment history

**## Finance Console**

\- Payment list

\- Refund

\- Reconciliation

**## FDE Debug Console**

\- Provider calls

\- Webhooks

\- trace\_id

\- errors

**## VCC Workflow Assistant**

\- Chat / Input

\- Parsed application

\- Approval

\- Card result

不得为了 UI 消耗大量项目时间。

\---

**# 21. 可观测性**

每个入口请求生成：

\`trace\_id\`

日志至少包含：

\`\`\`text

trace\_id

operation

local\_order\_id

provider\_request\_id

provider\_transaction\_id

provider

status

latency\_ms

error\_type

\`\`\`

结构化 JSON Log 优先。

禁止输出：

\- appSecret

\- access token

\- CVV

\- full PAN

\- 其他敏感信息

\---

**# 22. 测试要求**

**## 22.1 Unit Test**

必须：

\- state transition

\- credit ledger idempotency

\- CreditHold 结算与释放

\- refund validation

\- approval rule

\- adapter mapping

\- PII / Secret redactor

\- RBAC policy

\---

**## 22.2 Integration Test**

业务集成测试使用 Mock Adapter + Test DB。Sandbox Adapter 必须使用 httpx MockTransport / 固定官方契约样本做无 Secret 的协议映射测试；真实 Sandbox 验证不属于 CI。

**### TC01 — 正常支付 / 可信终态统一处理**

**Scenario A — Create 返回 PENDING**

Given：100 USD Topup，Create Payment Response = PENDING。

When：随后收到已验签 SUCCESS Webhook。

Then：

\- Payment = SUCCEEDED

\- Credits +100

\- TOPUP Ledger = 1

**Scenario B — Create 直接返回 SUCCESS**

Given：100 USD Topup，Create Payment Response = SUCCESS。

Then：

\- Create Response 通过同一 State Machine Service 将 Payment 迁移为 SUCCEEDED

\- Credits +100

\- TOPUP Ledger = 1

\- 后续再收到 SUCCESS Webhook 或 Query = SUCCESS 时，Credits 仍只入账一次

\---

**### TC02 — 重复支付请求**

同一幂等请求提交两次。

Then：

\- 只有一个逻辑 Payment

\- 不重复创建本地订单

\---

**### TC03 — Webhook 重复**

SUCCESS webhook × 10。

Then：

\- Credits 只增加一次

\---

**### TC04 — Webhook 乱序**

SUCCESS → PENDING。

Then：

\- 状态保持 SUCCEEDED

\---

**### TC05 — Webhook 丢失**

Payment Provider 已 SUCCESS，本地 PROCESSING。

When：reconcile

Then：

\- 本地变 SUCCEEDED

\- Credits +100

\---

**### TC06 — Provider Timeout**

Create Payment timeout。

Then：

\- Payment 保持 PROCESSING 并进入待查单状态

\- 保留原 partner\_transaction\_id / provider\_request\_id

\- 不能盲目重新创建新订单

\---

**### TC07 — HTTP 429**

Then：

\- retry policy 生效

\- 有最大 retry 次数

\- 有日志

\---

**### TC08 — Payment Fail**

Then：

\- FAILED

\- Credits 不增加

\---

**### TC09 — Refund**

SUCCEEDED 100 USD → Refund。

Then：

\- 先创建 CreditHold

\- RefundOrder = SUCCEEDED（UI 显示 REFUNDED）

\- Credit Ledger 产生一条 reversal，Hold = SETTLED

\---

**### TC10 — 重复退款**

同一 refund request 重复提交。

Then：

\- 只有一个逻辑 Refund

\- 只存在一个 CreditHold

\---

**### TC11 — Credits 不足退款**

用户已消费 Credits。

Then：

\- MANUAL\_REVIEW

\- balance 不为负数

\- 不调用 Checkout Provider

\---

**### TC12 — VCC Approval**

20,000 USD AWS。

Then：

\- Agent 解析成功

\- 必须 Approval

\- 未批准不能 Create Card

\---

**### TC13 — VCC Budget Fail**

60,000 USD AWS。

Then：

\- Budget rejected

\- 不调用 Issuing Provider

\---

**### TC14 — 幂等键 Payload 冲突**

同一 actor 对同一路由使用同一 Idempotency-Key，但第二次传入不同金额。

Then：

\- 409 Conflict

\- 无新增 Payment / Refund

\- 不调用 Provider

\---

**### TC15 — 并发入账**

10 个 SUCCESS Webhook 与一次 reconcile 并发执行。

Then：

\- Payment = SUCCEEDED

\- TOPUP Ledger = 1

\- Credits 只增加一次

\---

**### TC16 — RBAC 与脱敏**

Developer 尝试读取他人 Payment，或访问 Admin reconcile；同时处理包含 token / PII 的 Webhook。

Then：

\- 越权请求返回 403 / 404（按资源隐蔽策略）

\- 数据库、日志、测试快照均不含 token、PAN、CVV、姓名、邮箱、电话、IP 或客户动作 URL

\---

**# 23. 人工验收 Checklist**

陌生开发者只看 README，也应该能完成以下验收。

**## Setup**

\- [ ] Clone

\- [ ] \`.env.example\` → \`.env\`

\- [ ] 明确设置 \`PINGPONG\_MODE=mock\` 或 \`PINGPONG\_MODE=sandbox\`

\- [ ] 安装依赖

\- [ ] migrate

\- [ ] run

**## Sandbox（具备外部前置条件时优先验收）**

\- [ ] 已取得合法 Sandbox 测试账户、凭证和已开通的 Checkout 产品

\- [ ] HTTPS notify URL 可被 PingPong 访问

\- [ ] 已按实际账户契约完成客户支付动作

\- [ ] Create → Query / Webhook → Refund 真实调用成功

\- [ ] 保存不含 Secret、PII 或支付动作 URL 的验证证据

未具备上述条件时，只能执行下方 Mock 验收并标记 Sandbox Pending。

**## Payment**

\- [ ] 创建 100 USD Topup

\- [ ] 页面显示 PROCESSING

\- [ ] 触发 SUCCESS Mock Webhook

\- [ ] 页面变 SUCCEEDED

\- [ ] Credits = 100

**## Idempotency**

\- [ ] 使用同一 Idempotency-Key 重复创建 Topup

\- [ ] 相同 payload 返回同一 Payment

\- [ ] 不同 payload 返回 409

\- [ ] 重复发送同一 Webhook

\- [ ] Credits 仍为 100

**## Reconciliation**

\- [ ] 创建 Provider SUCCESS / Local PROCESSING 场景

\- [ ] 点击 Reconcile

\- [ ] Local 自动修复

**## Refund**

\- [ ] 退款

\- [ ] Refund = REFUNDED

\- [ ] Credits 正确回退

**## VCC**

\- [ ] 输入 AWS 20,000 USD 申请

\- [ ] Agent 输出结构化需求

\- [ ] 审批前不能开卡

\- [ ] Approve

\- [ ] Human Confirm

\- [ ] Mock Card 创建成功

\- [ ] Audit 可见

\---

**# 24. README 必须回答的问题**

README 不允许只写“如何启动”。

必须能够回答：

1\. 客户是谁？

2\. 客户为什么需要 PingPong？

3\. 为什么前端支付成功不能直接加 Credits？

4\. 如何处理 Webhook 丢失？

5\. 如何处理 Webhook 重复？

6\. 为什么需要幂等？

7\. 为什么 Provider Adapter 必须隔离？

8\. 如何排查一笔异常支付？

9\. Agent 为什么不能直接持有 PingPong Secret？

10\. VCC 为什么需要人工审批？

11\. Mock 与 Sandbox 的边界是什么？

12\. 哪些是 DemoAI 自定义规则，哪些来自 PingPong 官方 API？

13\. 为什么 Sandbox 是优先路径、Mock 又为何仍是自动化测试后备？

14\. 为什么 API 不接收 user\_id / role，如何实施 RBAC？

15\. 为什么不保存原始 Webhook payload 和支付动作 URL？

\---

**# 25. docs 输出要求**

**## docs/01-customer-scenario.md**

用 FDE 面向客户的语言描述：

\- 客户背景

\- Current State

\- Pain Points

\- Target State

\- Success Metrics

\---

**## docs/02-requirement-analysis.md**

至少包含：

\- Actors

\- Functional Requirements

\- Non-functional Requirements

\- Constraints

\- Out of Scope

\- Open Questions

\---

**## docs/03-solution-design.md**

至少：

\- Context Diagram

\- Component Diagram

\- Checkout Sequence

\- Webhook Sequence

\- Reconciliation Sequence

\- VCC Workflow Assistant Sequence

Mermaid 优先。

\---

**## docs/04-api-integration-guide.md**

模拟 FDE 给客户开发者的接入指南：

1\. 前置条件

2\. Environment

3\. Credential

4\. Authentication

5\. Create Payment

6\. Query

7\. Webhook

8\. Refund

9\. Idempotency

10\. Error Handling

11\. Sandbox Test

12\. Go-live

13\. next\_action 与 redirect / webhook 的职责边界

不得复制官方文档大段文字，应以自己的方案组织。

\---

**## docs/05-payment-state-machine.md**

解释：

\- Provider State

\- Domain State

\- State Mapping

\- Allowed Transition

\- Out-of-order Event

\- Payment 与 RefundOrder 的独立生命周期

\- AUTH\_SUCCESS 的 P0 处理策略

\---

**## docs/06-webhook-design.md**

解释：

\- verification

\- dedup

\- retry

\- ordering

\- consistency

\- security

\- ACK 策略、字段别名与敏感数据最小化

\---

**## docs/07-vcc-agent-design.md**

解释：

\- Agent Boundary

\- Tool

\- Approval

\- RBAC

\- Idempotency

\- Audit

\- Mock vs Sandbox

\---

**## docs/08-troubleshooting.md**

至少包含：

\| Symptom | Possible Cause | Check | Resolution |

\|---|---|---|---|

\| Payment 401 | auth/sign | credentials/sign | refresh/fix |

\| Payment stuck | webhook lost | query provider | reconcile |

\| Duplicate credit | webhook idempotency | ledger/event | dedup |

\| 429 | rate limit | call logs | backoff |

\| Timeout | network/provider | trace | query before retry |

\| Refund inconsistent | delayed event | refund query | reconcile |

\---

**## docs/09-test-plan.md**

完整列出 TC01\~TC16。

\---

**## docs/10-go-live-checklist.md**

至少：

**### Credential**

\- [ ] Production Credential via Secret Manager / env

\- [ ] No secret in repository

**### Network**

\- [ ] IP whitelist where required

\- [ ] HTTPS callback

**### Webhook**

\- [ ] Signature verification

\- [ ] Retry-safe

\- [ ] Idempotency

**### Consistency**

\- [ ] Active query / reconciliation

**### Security**

\- [ ] No PAN/CVV storage

\- [ ] Log masking

\- [ ] No raw Webhook payload / token / PII / payment action URL persistence

\- [ ] RBAC authorization tests passed

**### Observability**

\- [ ] trace\_id

\- [ ] provider request id

\- [ ] alert rule

**### Rollback**

\- [ ] feature flag / provider mode

\- [ ] ability to stop new payments

\---

**# 26. 非功能要求**

**## Reliability**

\- 第三方调用必须 timeout。

\- 状态变更必须事务化。

\- Credits 入账与幂等记录必须避免重复执行。

\- 外部创建调用与本地数据库事务分离；超时后必须查单，不得创建第二笔订单。

\- 退款外部调用前必须存在有效 CreditHold。

**## Maintainability**

\- Domain / Service / Adapter 分层明确。

\- 不为架构而架构。

\- 单文件建议 < 500 行；超过时考虑职责拆分。

**## Security**

\- Secret 不进 Git。

\- 敏感日志脱敏。

\- Agent 不拥有直接 Secret。

\- 原始 Webhook Body 只用于验签，不持久化；Provider 的请求 / 响应 Body 不得直接记录。

\- 所有受保护资源必须经 Principal + RBAC 校验；禁止客户端传入 user\_id / role 作为授权依据。

**## Developer Experience**

新开发者在 Mock 模式下应能够通过 README 快速运行。

\---

**# 27. Coding Agent 实施约束**

Coding Agent 必须遵守：

**## 27.1 Spec First**

\`SPEC.md\` 为需求 Source of Truth。

如果实现与 SPEC 冲突：

\- 优先修改实现。

\- 如果 SPEC 明显错误，先更新 SPEC 并说明原因。

\---

**## 27.2 Small Steps**

建议顺序：

\`\`\`text

1\. Skeleton

2\. Config / local demo authentication / RBAC

3\. DB Models + State Machine + Idempotency

4\. Sandbox Checkout Adapter contract mapping

5\. Mock Checkout Adapter

6\. Payment Service + Topup

7\. Webhook + Credits Ledger

8\. Reconciliation

9\. Refund + CreditHold

10\. Observability / redaction

11\. Tests

12\. FDE Docs

13\. VCC Workflow Assistant

\`\`\`

禁止一开始同时实现全部模块。

\---

**## 27.3 Test Before Done**

Coding Agent 不允许仅因为“代码写完”宣布任务完成。

每个 Story 完成至少：

\`\`\`text

Implement

→ Unit Test

→ Integration Test

→ Manual Verification where needed

→ Docs Update

\`\`\`

\---

**## 27.4 不允许伪造真实联调**

如果：

\- 没有 PingPong Sandbox Credential

\- 没有真实调用成功

必须写：

\`Mock integration based on official API contract.\`

不得写：

\`Successfully integrated PingPong Sandbox.\`

\---

**# 28. Implementation Stories**

**## Story P0-01 — Project Bootstrap**

Acceptance：

\- FastAPI 可启动

\- health endpoint

\- DB migration

\- pytest runnable

\- env config

\- PINGPONG\_MODE 显式配置，Sandbox 缺配置时 fail fast

\- 本地 Demo Authentication 与 Principal 依赖

\---

**## Story P0-02 — Payment Domain**

Acceptance：

\- PaymentOrder

\- RefundOrder / CreditLedger / CreditHold / ApiIdempotency / AuditLog

\- state machine

\- invalid transition test

\- 数据库唯一约束与并发入账测试

\---

**## Story P0-03 — Sandbox Checkout Adapter**

Acceptance：

\- 按当前官方 Checkout V4 文档实现鉴权、Create / Query / Refund 的字段映射

\- 将 Provider action 映射为 next\_action，不假定 checkout\_url

\- 不接受、不传递 PAN / CVV

\- Sandbox 缺少必需配置时启动 fail fast，不泄露 Secret

\- 使用 httpx MockTransport / 固定官方样本完成无 Secret 协议测试

\- 真实调用仅在外部 Sandbox 前置条件齐备时执行并保留脱敏证据

\---

**## Story P0-04 — Mock Checkout**

Acceptance：

Mock 必须实现与 Sandbox Adapter 相同的协议，并可配置：

\`\`\`text

success

fail

timeout

429

next\_action

\`\`\`

\---

**## Story P0-05 — Topup**

Acceptance：

\- 创建 order

\- 调 provider

\- Create Payment Response 必须作为可信 Provider Observation 进入统一 State Machine

\- PENDING/PROCESSING → PROCESSING；SUCCESS → SUCCEEDED + TOPUP Ledger 在本地事务边界内产生一次业务效果；AUTH\_SUCCESS / FAILED / FAIL / CANCEL / CLOSED / CLOSE 按统一映射处理

\- 不允许存在“Create Response 直接改余额”的旁路逻辑

\- Idempotency-Key、payload 冲突 409

\- 客户身份从 Principal 获取

\- next\_action 只在响应中返回

\---

**## Story P0-06 — Webhook + Credits**

Acceptance：

\- SUCCESS 入账

\- Duplicate 不重复

\- Out-of-order 不倒退

\- 签名失败、订单金额/币种不匹配不入账

\- 原始 payload / PII 不落库、不入日志

\---

**## Story P0-07 — Query + Reconciliation**

Acceptance：

\- 主动查询

\- LOCAL\_STALE 修复

\- audit log

\- timeout 后复用既有 Provider ID 查单

\---

**## Story P0-08 — Refund**

Acceptance：

\- full refund

\- query refund

\- reversal ledger

\- duplicate refund protection

\- CreditHold 结算 / 释放

\- Credits 不足时 MANUAL\_REVIEW 且不调用 Provider

\---

**## Story P0-09 — FDE Debug Console**

Acceptance：

可看到：

\- local order

\- provider id

\- trace

\- provider call

\- webhook

\- reconciliation

\---

**## Story P0-10 — Docs**

Acceptance：

\`docs/\` 10 个文档齐全并与实现一致。

\---

**## Story P1-01 — Finance Agent**

Acceptance：

自然语言 → Structured VCC Application。

必须覆盖缺字段。

\---

**## Story P1-02 — Approval**

Acceptance：

审批前无法执行 Create Card。

\---

**## Story P1-03 — Mock Issuing**

Acceptance：

\- create card

\- masked card only

\- idempotency

\- audit

\---

**## Story P1-04 — Issuing Sandbox Adapter**

仅在拥有合法凭证后实现。

Acceptance：

\- 使用真实 Sandbox

\- 自动化测试不得依赖 Production

\- 文档记录实际验证范围

\---

**# 29. Definition of Done**

P0 Core 完成必须同时满足：

\- [ ] Mock 模式完整跑通

\- [ ] Sandbox Checkout Adapter 协议映射与无 Secret 合约测试通过

\- [ ] P0 自动测试通过：TC01\~TC11、TC14\~TC16

\- [ ] 人工验收通过

\- [ ] README 可指导陌生开发者运行

\- [ ] 10 个 FDE docs 完成

\- [ ] 无 Secret

\- [ ] 无真实卡信息

\- [ ] Webhook 幂等

\- [ ] Credits Ledger 幂等

\- [ ] CreditHold 保证退款过程中余额不为负

\- [ ] 主动查单补偿可运行

\- [ ] Refund 可运行

\- [ ] Provider Call 可追踪

\- [ ] 原始 Webhook payload、PII、token、支付动作 URL 不落库、不入日志

\- [ ] RBAC 越权测试通过

Sandbox Verified 是优先但依赖外部环境的完成标记；在具备合法 Sandbox 前置条件时，必须额外满足：

\- [ ] Sandbox Create → 客户支付动作 → Webhook / Query → Refund 全链路真实调用成功

\- [ ] 使用当前已开通产品的真实 action / Hosted / Session 契约，未编造字段

\- [ ] HTTPS callback、验签、幂等与主动查单均被实际验证

\- [ ] 验证证据已脱敏，且 README 记录实际验证范围

无合法凭证或产品权限时，只能标记 P0 Core / Mock Verified 与 Sandbox Pending。

P1 完成：

\- [ ] Agent Structured Output

\- [ ] Budget

\- [ ] Approval

\- [ ] Human Confirm

\- [ ] Mock VCC

\- [ ] Audit

\- [ ] TC12\~TC13 通过

\---

**# 30. 面试演示脚本**

README 最后需要提供一个 10 分钟 Demo Script。

推荐：

**## 1 分钟：客户问题**

“DemoAI 面向全球开发者提供模型 API，需要全球收款；企业自身还存在海外云资源支出。”

**## 2 分钟：架构**

解释：

\- Payment Service

\- PingPong Adapter

\- Webhook

\- Ledger

\- Reconciliation

**## 3 分钟：支付**

\- 若 Sandbox Verified：展示 Topup 100 USD、Provider action、Webhook / Query 与 Credits 入账

\- 否则明确展示 Mock 模拟流程，不声称真实联调

\- 重复 Webhook

\- Credits 仍 +100

**## 2 分钟：异常**

\- 模拟 Webhook 丢失

\- 主动查单恢复

\- 展示 trace\_id

**## 2 分钟：VCC Workflow Assistant**

\- 输入 AWS 账单

\- Agent parse

\- approval

\- create mock VCC

\- audit

\---

**# 31. 简历可使用表述（完成后再使用）**

如果仅完成 Mock：

\> **\*\*跨境支付 API 集成 POC｜PingPong Checkout / VCC\*\***：基于 PingPong 官方 API 设计 AI 平台全球支付接入方案，实现收单支付创建、Webhook、主动查单、退款、幂等与异常补偿；设计财务系统至 VCC 用卡的 Agent 工作流，并输出开发者接入指南、排障手册和上线验收清单。

如果真实完成 Sandbox Checkout 联调：

\> **\*\*跨境支付 API 集成 POC｜PingPong Checkout / VCC\*\***：仅在确有真实 Sandbox 证据时，才可描述为基于 PingPong Sandbox 完成 Checkout API 联调；当前实现应描述为基于公开 Contract fixture/MockTransport 的 Checkout 适配、状态机、Webhook、退款、幂等及异常补偿，并实现带可选 LLM 意图解析的 VCC Workflow Assistant，用卡流程仍为 Mock。

仅当确实完成对应能力后，才允许使用上述描述。

\---

**# 32. 官方资料基线**

实现时以 PingPong 官方最新文档为准，不依赖本 SPEC 中可能随时间变化的字段细节。

当前验证到的公开资料基线：

1\. PingPong Checkout V4 Overview / Create Payment  

   https\://docs.pingpongx.com/api/acq/create-a-payment

2\. PingPong Checkout Webhook  

   https\://docs.pingpongx.com/api/webhooks/checkout-webhook

3\. PingPong API Sandbox / Product APIs  

   https\://docs.pingpongx.com/api/home/sandbox

4\. PingPong 开放平台快速接入  

   https\://open.pingpongx.com/docs/developer/guide/quick-access/

5\. PingPong Checkout Get Started / Sandbox Account  

   https\://docs.pingpongx.com/doc/checkout/online-payment/get-started/get-started

已公开文档明确强调的接入原则包括：

\- Test / Sandbox / Production 环境区分

\- Credential / Token / Authentication

\- API 错误码与异步通知

\- 异步通知不能作为唯一一致性保障，应对接主动查单

\- 注意接口调用频率 / 429

\- Checkout V4 Create Payment 支持 \`(partner\_transaction\_id, request\_id)\` 级别幂等语义

\- Checkout V4 Create Payment 的客户后续操作以 action 为准，redirect\_url 不是支付终态依据

\- Checkout Payment Provider 状态至少需映射 PENDING、SUCCESS、AUTH\_SUCCESS、FAIL、CLOSE

\- Sandbox 测试账户需要通过 PingPong 技术支持获取；未获得账户时不得伪造 Sandbox 验证结论

Coding Agent 每次实现真实 PingPong Adapter 前必须重新核对官方最新文档。

\---

**# 33. 最终原则**

本项目应始终遵循：

\> **\*\*Business First → Spec Driven → Design Before Code → Small Steps → Test Before Done\*\***

优先证明 FDE 能力，而不是堆技术栈。

项目最终价值不是：

\> “我调用过一个支付 API。”

而是：

\> **\*\*“我能站在客户技术接入负责人的视角，把一个跨境支付需求从需求澄清、方案设计、API 接入、异常处理、测试验收到开发者文档完整交付。”\*\***
