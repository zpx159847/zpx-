"""Generate reference and walkthrough from the same catalog used by the UI."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from catalog import CHALLENGES

header = """# 关卡清单

共 20 个关卡，9 个带业务逻辑标签。2025 为主要分类，2021 列用于旧版课程对照。

分类覆盖表示提供该风险的教学实例，不等同于覆盖全部 CWE。供应链、旧组件和风控依赖采用本地教学模型；旧组件不对应真实 CVE。

| ID | 关卡 | OWASP 2025 | OWASP 2021 | 业务逻辑 | 入口 |
| --- | --- | --- | --- | --- | --- |
"""
for c in CHALLENGES:
    header += f"| {c['id']} | {c['title']} | {c['category']} {c['category_name']} | {c['owasp2021']} | {'是' if c['logic'] else '—'} | `{c['endpoint']}` |\n"
header += "\nA03:2025 是扩大的供应链分类；旧组件是其一个示例。供应链清单与异常放行在 2021 中没有独立同名分类，以 — 标记，避免强行一一对应。SSRF 在 2021 为 A10，在 2025 归入 A01。\n"
(ROOT / "docs" / "CHALLENGES.md").write_text(header, encoding="utf-8")
walkthrough = """# 复现步骤与修复方向（含答案）

每关建议从页面「重置靶场」开始，使用 alice / Alice123!。不同漏洞会改变共享钱包、角色、密码和折扣；全局重置可避免互相影响。

请求体为 JSON，使用页面「接口实验台」发送，默认自动携带登录 Cookie。返回的 FLAG 大多自动记录；crypto 需要手动提交。XSS 需在浏览器实际执行留言页；本靶场没有防作弊机制。

"""
for i, c in enumerate(CHALLENGES, 1):
    walkthrough += f"## {i:02d}. {c['title']} · {c['id']}\n\n**入口：** `{c['endpoint']}`\n\n**目标：** {c['goal']}\n\n**复现：** {c['solution']}\n\n**修复：** {c['fix']}\n\n"
walkthrough += """## 推荐的修复练习

保留漏洞版本作为基线，在独立分支修复一个问题，并将相关测试从「断言漏洞可复现」改为「断言攻击被拒绝、正常流程仍成功」。例如退款测试应断言第二次退款返回 409，余额保持初始金额；单纯删除 FLAG 不算修复。

## 代理抓包

浏览器代理指向本机 Burp Suite，目标为自己的 http://127.0.0.1:8080。使用独立浏览器配置进行练习；若环回请求绕过代理，可使用专门的测试浏览器或直接在 Repeater 构造请求。每次切换账号重新获取 sid Cookie。
"""
(ROOT / "docs" / "WALKTHROUGH.md").write_text(walkthrough, encoding="utf-8")
print("Generated docs/CHALLENGES.md and docs/WALKTHROUGH.md")
