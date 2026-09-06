# Image2 生图工坊

一个本机运行的 `gpt-image-2` 生图 Web 小工具。程序**不内置任何中转站（提供商）与 API key**：两项只在网页界面填写，后端不读 `.env`、不读环境变量，也没有任何默认地址。未填写时前端直接拦下，后端返回 400，不会向任何服务器发请求。key 只随请求头使用，不写入日志与历史记录。

## 功能

- 输入提示词，分别选择“画幅”与“分辨率”、质量、数量后一键生图
- 画幅支持 `自动 / 1:1 / 4:3 / 3:4 / 16:9 / 9:16`；选“自动”时由模型根据提示词决定画幅（`size=auto`）
- 分辨率最高 `2K`（1K/1.5K/2K），选“自动”画幅时分辨率自动忽略
- 可上传一张或多张参考图，走 `/images/edits` 驱动模型按参考图生成
- 提供商地址（Base URL）与 API Key 全部由界面输入，两项默认为空、必填，填一次即记在浏览器本地
- 两项任一缺失时，前端提示“待配置”并聚焦对应输入框，后端同样拒绝，不会向任何默认地址发请求
- 结果实时预览，支持点击放大、单张下载
- 最近生图历史持久化在服务端 `outputs/history.json`，跨重启保留，历史项可直接下载或清空
- 后端先校验中转站 `/models`，确认模型列表包含 `gpt-image-2` 再生图
- 对 401/429/5xx/524 等常见错误给出中文可读提示；对 429/5xx 做有限重试，不对 `524`（Cloudflare 代理超时）盲目重试

## 快速开始

1. 安装依赖（Python 3.10+）：

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. 启动：

   ```powershell
   .\start.ps1
   ```

   浏览器打开 `http://127.0.0.1:8787`（端口可用 `PORT` 环境变量或 `--port` 参数修改）。

3. 在页面下方填写 **API Key** 与 **提供商地址（Base URL）**，两项都填好后状态灯会自动校验模型。
   配置只保存在本机浏览器 localStorage，程序目录里不需要任何配置文件。

## 配置项

生图配置（界面填写，无默认值）：

| 界面项 | 默认值 | 说明 |
| --- | --- | --- |
| API Key | 空（必填） | 你的中转站 API key |
| 提供商地址（Base URL） | 空（必填） | 中转站地址，通常以 `/v1` 结尾，勿填官方接口 |

服务配置（可选，环境变量 / 命令行）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `HTTP_PROXY` / `HTTPS_PROXY` | 无 | 需要走本地代理时设置，例如 `http://127.0.0.1:7897` |
| `PORT` | `8787` | 本服务监听端口，也可用 `python app.py --port 8123` |

## 说明

- 模型固定为 `gpt-image-2`；画幅与分辨率分别通过下拉框选择，两两组合派生实际 `宽x高`；选“自动”画幅时下发 `size=auto`。
- `gpt-image-2` 不支持 `background=transparent`，因此未暴露透明背景选项。
- 生成的图片保存在 `outputs/generated/`。
- 参考图上传后走中转站的 `/images/edits`；若你的中转站未开启该接口，会返回对应 4xx 错误提示。
- `524` 来自中转站前端 Cloudflare 的“源站读取超时”（约 120 秒），不是 key 或接口错误；出现时请稍后重试或改用 `auto`/低质量、更小尺寸。
- 如果返回 `401 invalid_api_key`，先确认界面里的 Base URL 指向你自己的中转站，而非官方地址。
- 连接超时通常是代理未设置或不通，检查 `HTTP_PROXY` / `HTTPS_PROXY`。

## 直接调用接口

后端也暴露了 API，供脚本或其它程序复用。因为不再有服务端配置，`base_url` 与 `api_key`
必须随请求一起传：

```powershell
$body = @{
  prompt = "high-end portrait, minimalist indoor background, soft natural light, no text"
  base_url = "https://你的中转站地址/v1"
  api_key = "你的中转站key"
  ratio = "3:4"
  k = "2K"
  quality = "high"
  n = 1
} | ConvertTo-Json

curl.exe "http://127.0.0.1:8787/api/generate" `
  -H "Content-Type: application/json" `
  -d $body
```

带参考图（multipart）：

```powershell
curl.exe "http://127.0.0.1:8787/api/generate" `
  -F "prompt=keep the subject but make the background pastel, no text" `
  -F "base_url=https://你的中转站地址/v1" `
  -F "api_key=你的中转站key" `
  -F "ratio=auto" `
  -F "quality=auto" `
  -F "n=1" `
  -F "image=@D:\path\to\ref.png;type=image/png"
```

## 打包为程序

运行 `build.ps1` 即可用 PyInstaller 生成单文件 Windows 程序：

```powershell
.\build.ps1
```

产物为 `dist\Image2Studio.exe`，`build.ps1` 还会把 `使用说明.txt` 复制进 `dist\`。打包版与源码运行一致，但路径行为不同：

- 前端静态资源（`static\`）已内置进 exe，无需随程序分发。
- **exe 内不含任何 key 与中转站地址**，也不读取 `.env`；使用者只需在网页界面填写两项。
- 生成的图片与历史写到 exe 同级 `outputs\generated\` 与 `outputs\history.json`，可持久化保存。
- 换端口：`Image2Studio.exe --port 8123`（默认 8787）。

分发时把 `Image2Studio.exe` 与 `使用说明.txt` 发给使用者即可：双击 exe，浏览器打开
`http://127.0.0.1:8787`，在页面下方填好自己的提供商地址与 API Key 就能生图。

## 项目规范

- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [LICENSE](LICENSE)（MIT）
- [SECURITY.md](SECURITY.md)
