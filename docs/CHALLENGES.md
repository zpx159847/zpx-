# 关卡清单

共 20 个关卡，9 个带业务逻辑标签。2025 为主要分类，2021 列用于旧版课程对照。

分类覆盖表示提供该风险的教学实例，不等同于覆盖全部 CWE。供应链、旧组件和风控依赖采用本地教学模型；旧组件不对应真实 CVE。

| ID | 关卡 | OWASP 2025 | OWASP 2021 | 业务逻辑 | 入口 |
| --- | --- | --- | --- | --- | --- |
| idor | 隔壁的订单 | A01 访问控制失效 | A01 | — | `GET /api/orders/1002` |
| mass | 自己给自己升职 | A01 访问控制失效 | A01 | — | `POST /api/profile` |
| ssrf | 预览器背后的内网 | A01 访问控制失效 | A10 | — | `GET /api/preview?url=...` |
| debug | 忘关的调试面板 | A02 安全配置错误 | A05 | — | `GET /debug` |
| supply | 来路不明的促销插件 | A03 软件供应链失效 | — | — | `POST /api/plugins/install` |
| crypto | 编码不是加密 | A04 加密机制失效 | A02 | — | `GET /api/exports/customers` |
| sqli | 万能登录口令 | A05 注入 | A03 | — | `POST /api/login` |
| xss | 会执行的商品留言 | A05 注入 | A03 | — | `POST /api/reviews · GET /reviews` |
| price | 一分钱买键盘 | A06 不安全设计 | A04 | 是 | `POST /api/orders` |
| negative | 负数也能下单 | A06 不安全设计 | A04 | 是 | `POST /api/orders` |
| coupon | 无限新客优惠 | A06 不安全设计 | A04 | 是 | `POST /api/coupons/redeem` |
| reset | 重置别人的密码 | A07 身份认证失效 | A07 | 是 | `POST /api/reset/confirm` |
| cookie | 会员 Cookie 的秘密 | A08 软件或数据完整性失效 | A08 | — | `GET /api/vip` |
| audit | 没人听见的失败登录 | A09 安全日志与告警失效 | A09 | — | `GET /api/audit/status` |
| failopen | 风控异常，直接放行 | A10 异常条件处理不当 | — | 是 | `POST /api/risk/check` |
| payment | 自己签收支付成功 | A08 软件或数据完整性失效 | A08 | 是 | `POST /api/payments/callback` |
| workflow | 没付款先发货 | A06 不安全设计 | A04 | 是 | `POST /api/orders/{id}/ship` |
| refund | 一单退两次 | A06 不安全设计 | A04 | 是 | `POST /api/orders/{id}/refund` |
| csrf | 点击链接就换邮箱 | A01 访问控制失效 | A01 | 是 | `GET /api/profile/email?email=...` |
| component | 旧模板组件的路径穿越 | A03 软件供应链失效 | A06 | — | `GET /api/legacy-template?name=...` |

A03:2025 是扩大的供应链分类；旧组件是其一个示例。供应链清单与异常放行在 2021 中没有独立同名分类，以 — 标记，避免强行一一对应。SSRF 在 2021 为 A10，在 2025 归入 A01。
