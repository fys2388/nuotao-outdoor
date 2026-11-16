# deploy-b2b-pages.ps1
# 一键构建 + 部署 frontend-b2b 到 Cloudflare Pages。
#
# 用法(二选一):
#   1) 已有 token:  $env:CLOUDFLARE_API_TOKEN = "<你的token>"; .\deploy-b2b-pages.ps1
#   2) 传参:        .\deploy-b2b-pages.ps1 -ApiToken "<你的token>"
#
# 可选参数:
#   -ProjectName   Cloudflare Pages 项目名(默认 nuotao-b2b)
#   -SkipBuild     跳过构建,直接部署已有 dist(默认 $false)
#
# 说明:
#   - 部署方式为 "direct upload"(把 dist 目录直接上传到 Pages),不依赖 GitHub。
#   - 首次运行会创建 Pages 项目 nuotao-b2b,访问地址 https://nuotao-b2b.pages.dev。
#   - token 需要 Cloudflare Pages + Workers 相关权限(模板 "Edit Cloudflare Workers" 即可)。

[CmdletBinding()]
param(
  [string]$ApiToken = $env:CLOUDFLARE_API_TOKEN,
  [string]$ProjectName = "nuotao-b2b",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

# ---- 0. 前置检查 ----
if ([string]::IsNullOrWhiteSpace($ApiToken)) {
  Write-Host "[X] 未提供 Cloudflare API Token。" -ForegroundColor Red
  Write-Host "    请先执行:  `$env:CLOUDFLARE_API_TOKEN = \"<你的token>\"  再运行本脚本。" -ForegroundColor Yellow
  Write-Host "    或传参:    .\deploy-b2b-pages.ps1 -ApiToken \"<你的token>\"" -ForegroundColor Yellow
  exit 1
}
$env:CLOUDFLARE_API_TOKEN = $ApiToken

$repoRoot = Split-Path -Parent $PSScriptRoot
$feDir = Join-Path $repoRoot "frontend-b2b"
$distDir = Join-Path $feDir "dist"

if (-not (Test-Path $feDir)) {
  Write-Host "[X] 找不到前端目录: $feDir" -ForegroundColor Red
  exit 1
}

Write-Host "==> 项目: $ProjectName" -ForegroundColor Cyan
Write-Host "==> 前端目录: $feDir" -ForegroundColor Cyan

# ---- 1. 安装依赖 ----
if (-not $SkipBuild) {
  Write-Host "`n==> [1/3] 安装依赖 (npm install)..." -ForegroundColor Cyan
  Push-Location $feDir
  try {
    if (-not (Test-Path "node_modules")) {
      npm install
      if ($LASTEXITCODE -ne 0) { throw "npm install 失败" }
    } else {
      Write-Host "    node_modules 已存在,跳过安装。"
    }
  } finally {
    Pop-Location
  }

  # ---- 2. 构建 ----
  Write-Host "`n==> [2/3] 构建 (npm run build)..." -ForegroundColor Cyan
  Push-Location $feDir
  try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "构建失败" }
  } finally {
    Pop-Location
  }

  if (-not (Test-Path (Join-Path $distDir "index.html"))) {
    Write-Host "[X] 构建产物缺失: $distDir\index.html" -ForegroundColor Red
    exit 1
  }
  Write-Host "    构建完成: $distDir" -ForegroundColor Green
} else {
  Write-Host "`n==> [跳过构建] 直接使用 $distDir" -ForegroundColor Yellow
  if (-not (Test-Path (Join-Path $distDir "index.html"))) {
    Write-Host "[X] 找不到 $distDir\index.html,请先构建。" -ForegroundColor Red
    exit 1
  }
}

# ---- 3. 部署到 Cloudflare Pages ----
Write-Host "`n==> [3/3] 部署到 Cloudflare Pages (项目: $ProjectName)..." -ForegroundColor Cyan
Write-Host "    (首次运行会自动创建项目,访问地址 https://$ProjectName.pages.dev)" -ForegroundColor Gray

wrangler pages deploy "$distDir" --project-name="$ProjectName" --branch="main" --commit-dirty=true

if ($LASTEXITCODE -ne 0) {
  Write-Host "[X] 部署失败(见上方 wrangler 报错)。" -ForegroundColor Red
  Write-Host "    常见原因: token 权限不足(需 Cloudflare Pages + Workers 权限)。" -ForegroundColor Yellow
  exit 1
}

Write-Host "`n=========================================" -ForegroundColor Green
Write-Host " 部署成功!" -ForegroundColor Green
Write-Host " pages.dev : https://$ProjectName.pages.dev" -ForegroundColor Green
Write-Host " 自定义域名: https://b2b.nuotaooutdoor.com  (已绑定)" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
