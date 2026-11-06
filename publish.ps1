param([string]$Repository = 'https://github.com/zpx159847/zpx-.git')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.git')) {
    git init -b main
    if ($LASTEXITCODE -ne 0) { throw 'git init 失败' }
    git remote add origin $Repository
}
$actualRemote = git remote get-url origin
if ($actualRemote -ne $Repository) { throw "当前 origin 为 $actualRemote，未推送到非预期仓库。" }
git add -- app tests tools docs data/.keep .github Dockerfile compose.yaml compose.pull.yaml .dockerignore .gitignore .gitattributes .env.example README.md LICENSE start.ps1 start.sh publish.ps1
if ($LASTEXITCODE -ne 0) { throw 'git add 失败' }
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m 'Add Pocket Lab OWASP training environment and GHCR workflow'
    if ($LASTEXITCODE -ne 0) { throw 'git commit 失败；请检查 Git 用户名和邮箱配置。' }
}
git push -u origin main
if ($LASTEXITCODE -ne 0) { throw '推送失败；请登录具有仓库及 workflow 写入权限的 GitHub 账号，再运行此脚本。不会强制覆盖远端。' }
Write-Host '代码已推送。请在仓库 Actions 查看构建；成功后镜像位于 ghcr.io/zpx159847/zpx-:latest。'
