# Customer Scenario

虚构客户 DemoAI 为全球开发者提供模型 API，以 USD Credits 预充值。收入侧需要 Checkout Create、Query、Webhook、幂等、查单和退款；支出侧希望把 AWS 等账单的虚拟卡申请、预算校验、审批和开卡审计串成可解释流程。

本 POC 首期只实现 USD，1 USD = 1 USD_CREDIT，不处理真实资金、KYC/KYB、PCI 卡数据或自动续费。

