# 验证记录 · 2026-11-06

## 已完成

- Windows 本机 Python 3.11.9：`python tests/test_lab.py`，28 项 HTTP 集成测试全部通过，含正常可信清单与合法管理员不误计通关的对照。
- 测试实际检查越权返回的订单、角色变化、可逆导出、SQL 登录绕过、负数下单余额、优惠券重复到账、小额回调、未付款发货、重复退款、密码接管、风控异常放行与完整重置；不是只检查 HTTP 200。
- 模板读取边界和 SSRF 出口沙箱也有拒绝路径测试，应用不读取真实宿主文件或任意远程地址。
- JavaScript 使用 `node --check app/static/app.js` 检查语法。
- 本地应用浏览器检查：Alice 账号登录、接口实验台提交留言、浏览器打开 `/reviews` 实际执行同源证明请求，随后界面显示 1/20、XSS 卡片已完成；完成后用页面重置，确认恢复 0/20 且旧登录失效。
- 截图：`screenshots/shop.jpg` 与 `screenshots/xss-verified.jpg`。检查使用当时的浏览器默认窄窗口，不代表所有设备均经过验证。
- 离线镜像归档：官方 Python 基础镜像 index 和 amd64 manifest 已按 SHA256 固定；校验基础层下载摘要、解压 DiffID、最终 config ImageID、5 个层与应用文件摘要。详情见本地交付 `dist/image-report.json`。
- GitHub Actions 的 [verify 作业](https://github.com/zpx159847/zpx-/actions/runs/42158550465/job/127698421983) 已完成真实 `docker build/run`，只读根文件系统加命名数据卷、UID 10001；28 项 HTTP 检查通过。
- 同一 verify 作业还调用打包器生成归档，实际执行 `docker load`，再对导入的镜像运行 28 项 HTTP 检查，全部通过。两个 Compose 配置也通过 `docker compose config --quiet`。
- [最终成功工作流](https://github.com/zpx159847/zpx-/actions/runs/42158771841)：代码提交 `0bf43110b214`，verify 和 publish 均成功；`ghcr.io/zpx159847/owasp-pocket-lab:latest` 与 `1.0.0` 已发布，含 linux/amd64、linux/arm64。
- GHCR 匿名验证通过：无需 GitHub 登录取得拉取令牌，读取两个架构的 manifest 与 config，校验 UID=10001 和代码 revision；amd64 的 7 个压缩层共 43,297,930 字节实际匿名下载并逐项验证 SHA256。`latest` 与 `1.0.0` index digest 均为 `sha256:7c6813e7d06612ec6252fc3b212d5a95463b0367ee38a960f3519bd30c4d58fa`，详情见 `registry-verification.json`。

## 尚未完成的外部验证

- 打包本机没有 Docker Engine、Docker Desktop 或可用 WSL，因此**没有在本机执行 `docker build`、`docker load` 或 `docker run`**。
- 本机离线归档按 Docker image save 格式直接组装。等价归档的导入和容器运行已在 CI 验证；本机交付文件本身只进行摘要和配置验证，`image-report.json` 的运行测试字段针对本机文件。
- GitHub 源码和 GHCR 镜像均已公开发布；匿名清单访问及 amd64 层下载已经验证。本机没有 Docker，匿名下载验证使用 Registry API，不声称在本机执行过 Docker CLI。
- CI 中的真实 amd64 容器会重复 HTTP 测试，并验证运行 UID=10001；通过后才发布多架构镜像。ARM64 镜像配置为构建发布，尚无 ARM 运行验证。

## 复现

```sh
python tests/test_lab.py
node --check app/static/app.js
python tools/build_archive.py
```

`LAB_TEST_URL` 可把测试指向单独的容器实例，但测试会反复重置数据。请使用可销毁的测试实例。
