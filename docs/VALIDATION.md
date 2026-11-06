# 验证记录 · 2026-11-06

## 已完成

- Windows 本机 Python 3.11.9：`python tests/test_lab.py`，28 项 HTTP 集成测试全部通过，含正常可信清单与合法管理员不误计通关的对照。
- 测试实际检查越权返回的订单、角色变化、可逆导出、SQL 登录绕过、负数下单余额、优惠券重复到账、小额回调、未付款发货、重复退款、密码接管、风控异常放行与完整重置；不是只检查 HTTP 200。
- 模板读取边界和 SSRF 出口沙箱也有拒绝路径测试，应用不读取真实宿主文件或任意远程地址。
- JavaScript 使用 `node --check app/static/app.js` 检查语法。
- 本地应用浏览器检查：Alice 账号登录、接口实验台提交留言、浏览器打开 `/reviews` 实际执行同源证明请求，随后界面显示 1/20、XSS 卡片已完成；完成后用页面重置，确认恢复 0/20 且旧登录失效。
- 截图：`screenshots/shop.jpg` 与 `screenshots/xss-verified.jpg`。检查使用当时的浏览器默认窄窗口，不代表所有设备均经过验证。
- 离线镜像归档：官方 Python 基础镜像 index 和 amd64 manifest 已按 SHA256 固定；校验基础层下载摘要、解压 DiffID、最终 config ImageID、5 个层与应用文件摘要。详情见本地交付 `dist/image-report.json`。

## 尚未完成的外部验证

- 打包本机没有 Docker Engine、Docker Desktop 或可用 WSL，因此**没有在本机执行 `docker build`、`docker load` 或 `docker run`**。
- 离线归档是按 Docker image save 格式直接组装，不是经 Docker daemon 导出的镜像。结构、摘要与配置已验证，实际导入和容器运行仍需验证。
- GitHub 仓库写入与 GHCR 发布需要该账户登录权限。配置已写入 `.github/workflows/container.yml`，但未经成功 Actions 运行，不能声称镜像已可拉取。
- CI 中的真实 amd64 容器会重复 HTTP 测试，并验证运行 UID=10001；通过后才发布多架构镜像。ARM64 镜像配置为构建发布，尚无 ARM 运行验证。

## 复现

```sh
python tests/test_lab.py
node --check app/static/app.js
python tools/build_archive.py
```

`LAB_TEST_URL` 可把测试指向单独的容器实例，但测试会反复重置数据。请使用可销毁的测试实例。
