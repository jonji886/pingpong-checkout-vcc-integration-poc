# Product Feedback

本文只记录本次基于 PingPong 当前公开文档和本地 Adapter 实现观察到的集成反馈，不把 Sandbox 未验证项描述为产品缺陷。

## Finding 1

### 问题

公开资料同时存在历史 Checkout V4 `prePay` envelope/path 和当前统一 Checkout `/api/acq/v4/...` contract。两者的 endpoint、鉴权头、请求 envelope 和客户动作字段不同。

### 客户影响

接入团队容易把 `accId/clientId/salt`、`Authorization/sign/sign-version`、`paymentUrl` 和 `action.redirect_url` 混用，导致请求在错误产品路径上失败，或错误地把创建 Session 当成支付成功。

### 当前 Workaround

本项目按版本隔离 DTO、Auth、Adapter 和 fixture；当前工厂只选择 Unified Adapter，历史实现显式标记为 `Legacy Public Sandbox`。Session 创建统一映射为 `PROCESSING`，支付终态只由 Webhook/Query 推进。

### 建议产品改进

在 Developer Docs 首页增加明显的产品版本/路径迁移表，并为每条 API 显示完整的认证模式、环境 Host、response envelope 和客户动作字段；对 Legacy 页面增加下线或迁移提示。

### 优先级

P1

### 原因

这是一次真实接入中会直接影响首个请求成功率和状态一致性的文档体验问题；本结论来自公开页面之间的 Contract 差异，不代表 PingPong 服务运行异常。

## Finding 2

### 问题

Issuing v2 Create Card 需要具体 `card_product_code`，文档说明该产品代码需要向 account manager 获取；创建接口还注明能力按客户审批开放。

### 客户影响

客户无法仅凭公开文档完成从注册到首张测试卡的自助 POC，接入排期依赖产品开通、卡产品配置和签名密钥准备。

### 当前 Workaround

本项目把 `PINGPONG_ISSUING_CARD_PRODUCT_CODE` 作为显式配置，没有默认猜测值；HTTP Adapter 完成 Contract serialization/parsing，Mock Adapter 用于本地 E2E，Sandbox 状态保持 Pending。

### 建议产品改进

提供带可用测试 `card_product_code` 的 Sandbox 示例账户、Create → Detail → Action → Transaction Query 最小样例，以及 signer 配置和回调验收清单。

### 优先级

P1

### 原因

这会阻塞新客户从 Contract Verified 进入 Sandbox Verified，但具体开通策略属于账户/产品配置，不应由 SDK 猜测或绕过。

## Finding 3

### 问题

Issuing Card Detail 公开响应包含 `card_number` 和 `cvc` 等敏感字段；业务 POC 通常只需要卡 ID、状态和 masked card。

### 客户影响

如果接入方把 Provider 原始 JSON 直接写入日志、数据库或 LLM 上下文，敏感信息暴露面会扩大，且容易越过 PCI/内部权限边界。

### 当前 Workaround

Adapter DTO → Domain Mapper 只输出 `provider_card_id`、状态和 masked card；测试 fixture 可包含文档样本，但业务返回不包含 PAN/CVC，LLM 不接收 Provider payload。

### 建议产品改进

提供按 scope 控制的敏感字段返回策略，默认返回 masked card；在 API 示例旁明确标注 PAN/CVC 的保管、权限和日志禁止规则。

### 优先级

P0

### 原因

这是资金和卡数据安全边界，属于接入设计必须显式处理的风险；本反馈不声称 PingPong 文档字段本身错误。
