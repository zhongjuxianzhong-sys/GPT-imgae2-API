# 启动脚本：只负责拉起后端服务。提供商地址与 API Key 在网页界面填写，程序不读 .env。
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# 需要走本机代理时，启动前先设置 $env:HTTP_PROXY / $env:HTTPS_PROXY。
# 需要换端口时设置 $env:PORT，或改用 python app.py --port 8123。
$port = if ($env:PORT) { $env:PORT } else { "8787" }
Write-Host "正在启动 Image2 生图工坊：http://127.0.0.1:$port" -ForegroundColor Cyan
Write-Host "请在页面下方填写提供商地址（Base URL）与 API Key。" -ForegroundColor DarkGray
python "app.py"
