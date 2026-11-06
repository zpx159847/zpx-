$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw '请先安装并启动 Docker Desktop，切换到 Linux containers。' }
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw '构建或启动失败，请检查上方 Docker 输出。' }
Write-Host '靶场地址：http://127.0.0.1:8080' -ForegroundColor Green
