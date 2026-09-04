# 一键打包为 Windows 单文件程序。
# 产物：dist\Image2Studio.exe + dist\使用说明.txt
# 提供商地址与 API Key 只由使用者在网页界面填写：exe 内不含任何 key 与中转站地址，
# 源码目录的 .env 既不会被打包，也不会被复制到 dist。
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# 确保依赖已安装
python -m pip install --disable-pip-version-check -r requirements.txt
python -m pip install --disable-pip-version-check pyinstaller

Write-Host "开始打包..." -ForegroundColor Cyan
python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name Image2Studio `
  --add-data "static;static" `
  app.py

# 随程序分发使用说明。
Copy-Item -LiteralPath (Join-Path $Root "使用说明.txt") -Destination (Join-Path $Root "dist\使用说明.txt") -Force

# 防呆：dist 目录里不该出现任何 .env 配置文件。
$staleEnv = Join-Path $Root "dist\.env"
if (Test-Path -LiteralPath $staleEnv) {
  Remove-Item -LiteralPath $staleEnv -Force
  Write-Host "已删除 dist\.env（打包不携带任何 key）。" -ForegroundColor Yellow
}

Write-Host "打包完成：$Root\dist\Image2Studio.exe" -ForegroundColor Green
Get-ChildItem -LiteralPath (Join-Path $Root "dist") -Force |
  Where-Object { -not $_.PSIsContainer } |
  ForEach-Object { Write-Host ("  {0}  {1:N0} 字节" -f $_.Name, $_.Length) }
Write-Host "分发 dist 目录内容即可；使用者双击 exe，浏览器打开 http://127.0.0.1:8787" -ForegroundColor Yellow
