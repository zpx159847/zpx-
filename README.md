# Pocket Lab · 口袋漏洞靶场

一个可重置的中文商城靶场：**20 个关卡、OWASP Top 10:2025 十类风险、9 个业务逻辑练习**，同时提供 2021 分类对照。Python 标准库 + SQLite，应用无第三方运行依赖，单容器启动。

这是故意不安全的教学应用，只在本机或隔离环境使用。默认端口绑定 `127.0.0.1`；不要将端口暴露到公网，不要放入真实数据。

## 1. 本地构建启动

需要 Docker Engine / Docker Desktop（Linux containers）及 Compose v2。

```sh
docker compose up -d --build
```

打开 **http://127.0.0.1:8080**。Windows 也可在工程目录运行 `powershell -ExecutionPolicy Bypass -File .\start.ps1`；Linux/macOS 可运行 `sh start.sh`。

账号：

| 用户名 | 密码 | 身份 |
| --- | --- | --- |
| alice | Alice123! | 普通用户 |
| bob | Bob123! | 普通用户 |
| admin | Admin123! | 管理员 |

初始钱包 1000 元；欢迎券 `WELCOME50`。金额接口单位为**分**。订单 1001 属于 Alice，1002 属于 Bob。所有地址、客户记录与密钥均为虚构。

端口冲突时，复制 `.env.example` 为 `.env`，修改 `LAB_PORT=18080`，再启动并访问相应端口。

## 2. 导入随附的离线镜像

交付目录 `dist/` 包含已打包的 Linux amd64 镜像归档和 `SHA256SUMS.txt`：

```sh
docker load -i dist/pocket-lab-1.0.0-linux-amd64.tar.gz
docker compose up -d --no-build
```

这条路径不需要从 GitHub 拉源码或本地构建。归档通过官方 Python 基础层组装，校验层摘要、配置和应用文件；**打包机没有 Docker，因此归档的实际 `docker load/run` 尚待容器环境验证**。详见 `docs/VALIDATION.md` 和 `dist/image-report.json`。ARM 机器优先使用发布后的多架构镜像，或本地构建。

如果只有镜像文件，没有 Compose 文件：

```sh
docker run -d --name pocket-lab -p 127.0.0.1:8080:8080 -v pocket-lab-data:/data --read-only --tmpfs /tmp:size=32m --cap-drop ALL --security-opt no-new-privileges --pids-limit 96 --memory 256m pocket-lab:1.0.0
```

## 3. GitHub 仓库与可直接拉取的镜像

目标代码仓库：[zpx159847/zpx-](https://github.com/zpx159847/zpx-)。目标容器地址：`ghcr.io/zpx159847/zpx-`。

**只有仓库 Actions 构建并推送成功后，下面的镜像地址才可用；代码仓库地址本身不是容器镜像。**

`.github/workflows/container.yml` 会在 `main` 推送时：

1. 运行 HTTP 回归测试。
2. 构建并启动真实 amd64 容器，在只读根文件系统、非 root 用户下重复全部 HTTP 测试。
3. 通过测试后发布 `linux/amd64` 和 `linux/arm64` 镜像到 GHCR，包含 `latest`、`1.0.0` 与提交标签。

需要先登录有该仓库写入权限的 GitHub 账号。首次上传可运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\publish.ps1
```

脚本只提交工程白名单文件，不上传测试数据库、访问日志、镜像缓存或离线大文件；不执行强制推送。若本机尚未配置 Git 作者信息，请在本工程内配置 `git config user.name` 和 `git config user.email`。

在 [Actions](https://github.com/zpx159847/zpx-/actions) 等待工作流变绿。首次 GHCR 包通常是私有的；如需要**不登录直接拉取**，在 [该账户的 Packages](https://github.com/zpx159847?tab=packages) 打开 `zpx-` → Package settings → Change visibility → Public。公开源码不会自动保证容器包公开。若保留私有，需要在使用机器上 `docker login ghcr.io`。

发布成功后：

```sh
docker pull ghcr.io/zpx159847/zpx-:latest
docker run -d --name pocket-lab -p 127.0.0.1:8080:8080 -v pocket-lab-data:/data --read-only --tmpfs /tmp:size=32m --cap-drop ALL --security-opt no-new-privileges --pids-limit 96 --memory 256m ghcr.io/zpx159847/zpx-:latest
```

也可使用只含镜像引用的配置：

```sh
docker compose -f compose.pull.yaml up -d
```

如遇 `permission_denied: write_package`，检查 Actions 的 `packages: write` 权限与该包是否已关联仓库；Dockerfile 已包含 source 标签。Actions 工作流使用 GitHub 自动提供的 `GITHUB_TOKEN`，无需把 PAT 写进代码。

## 4. 练习方法

登录 Alice → 浏览商城并下单 → 打开「关卡地图」选择目标 → 展开分级提示 → 在「接口实验台」修改请求。实验台自动携带当前登录 Cookie，也支持直接用 Burp Suite 抓包修改。

命中漏洞后大多数关卡自动点亮；加密关卡需把解码后的 FLAG 粘贴到关卡页提交。存储型 XSS 需保存留言后在浏览器打开 `/reviews`，执行页面中的证明请求。

实例采用**单人共享进度**，不提供比赛防作弊、账号间独立计分或多租户隔离。提示、源码和 FLAG 均可读，适合练习与修复复核。

详细分类见 [关卡清单](docs/CHALLENGES.md)；需要答案时再看 [复现与修复建议](docs/WALKTHROUGH.md)。建议每个业务流程独立重置后练习：促销插件修改的折扣等状态会影响后续订单。

## 5. 重置、停止与持久化

页面右下「重置靶场」可恢复账号密码、钱包、订单、插件配置、留言及通关记录，并清除旧会话。

```sh
docker compose logs -f
docker compose stop
docker compose up -d
```

数据库保存在 Docker 命名卷，普通停止或重建保留数据。想从 Docker 层彻底删除该实例的数据时：

```sh
docker compose down -v
```

使用 `compose.pull.yaml` 启动的实例，请在这些 Compose 命令中保持 `-f compose.pull.yaml`。不要对其他项目的卷运行删除命令。

## 6. 教学范围

- SQL 注入、存储型 XSS、越权、Cookie 篡改、CSRF、价格与状态机错误等在应用中实际存在。
- SSRF 会真实发送内部 HTTP 请求，出口只允许靶场内 `127.0.0.1:9091/metadata`，不访问真实云元数据或任意外部站点；9091 不映射到宿主机。
- 供应链关卡信任未签名的**本地声明式插件清单**并改变结算规则；不下载、不执行外部代码。旧组件关卡使用自制 `LegacyTemplate 0.1-demo`，没有真实第三方 CVE，文件读取限制在虚构 fixtures 中。
- A09 用失败计数与缺失的安全事件、告警对比，演示日志不足；访问日志依然存在。A10 用解析异常演示风控默认放行。
- 本项目通过示例覆盖十类风险，不代表实现每个类别内的所有漏洞，也不是生产部署模板。

## 7. 开发与验证

本地 Python 3.11+ 可运行，默认仅监听环回地址：

```sh
python app/app.py
python tests/test_lab.py
```

对**独立、可销毁的测试容器**运行同一套检查（会逐项重置数据）：

```sh
LAB_TEST_URL=http://127.0.0.1:8080 python tests/test_lab.py
```

Windows PowerShell 用 `$env:LAB_TEST_URL='http://127.0.0.1:8080'` 再运行 Python；完成后 `Remove-Item Env:LAB_TEST_URL`。不要指向需要保留数据的实例。

`python tools/build_archive.py` 可在无 Docker 的机器上重新组装 amd64 归档；`--arch arm64` 组装 ARM 归档。该工具不代替容器运行测试。

## 官方参考

- [OWASP Top 10:2025 分类](https://top10.owasp.org/2025/0x00_2025-Introduction/)
- [OWASP Top 10:2021 分类](https://owasp.org/Top10/2021/)
- [GitHub Actions 发布容器镜像](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
- [GHCR 可见性与认证](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Docker load](https://docs.docker.com/reference/cli/docker/image/load/)
