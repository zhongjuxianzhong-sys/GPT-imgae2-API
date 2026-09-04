"""Image2 生图工坊 - Flask 后端。

职责：
  * 中转站地址（提供商）与 API key 只从前端界面输入，后端不读 .env、不读环境变量、不内置任何提供商。
  * 绝不把 API key 返回给前端，也不写入日志与历史记录。
  * 调用 POST {base_url}/images/generations（model=gpt-image-2）。
  * 解码 b64_json（或转存 url 指向的图片）到 outputs/generated/。
  * 托管前端页面与已生成图片。
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, request, send_from_directory


# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
# PyInstaller 打包后：静态资源解压到临时目录（_MEIPASS），只读；
# 而 outputs / history 必须写到 exe 旁边的持久目录。
IS_FROZEN = bool(getattr(sys, "frozen", False))

if IS_FROZEN:
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)).resolve()
    APP_DIR = Path(sys.executable).resolve().parent
else:
    RESOURCE_DIR = Path(__file__).resolve().parent
    APP_DIR = RESOURCE_DIR

# 静态资源目录（源码项目内 / 打包内置目录）。
STATIC_DIR = RESOURCE_DIR / "static"

OUTPUT_DIR = APP_DIR / "outputs" / "generated"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MODEL = "gpt-image-2"

# 未配置时给前端的统一提示，避免出现含糊的连接错误。
MISSING_BASE_URL_ERROR = "未填写提供商地址。请在页面下方输入中转站 Base URL（通常以 /v1 结尾）。"
MISSING_KEY_ERROR = "未填写 API key。请在页面下方输入中转站 API key。"

VALID_QUALITIES = {"auto", "low", "medium", "high"}

# 不少中转站通过 Cloudflare/WAF 按 User-Agent 过滤脚本访问。
# 统一使用浏览器 UA，避免 /models 与 /images/generations 被拦成 403 "Just a moment..."。
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
HTTP = requests.Session()
HTTP.headers.update(_BROWSER_HEADERS)

# 画幅（几比几）与档位（几K）。分辨率最高 2K。
# "auto" 表示由模型根据提示词自动决定画幅（下游 size=auto），此时忽略分辨率档位。
RATIOS = ["auto", "1:1", "4:3", "3:4", "16:9", "9:16"]
K_LEVELS = ["1K", "1.5K", "2K"]

# 各档位对应的“长边”像素数。
K_LONG_EDGE = {"1K": 1024, "1.5K": 1536, "2K": 2048}

OUTPUTS_ROOT = APP_DIR / "outputs"
HISTORY_FILE = OUTPUTS_ROOT / "history.json"
HISTORY_LIMIT = 100

# 生图请求等待中转站回包的上限。中转站常被 Cloudflare 以约 120s 的
# "源站读取超时"拦截（524），因此客户端超时要略高于该窗口，避免客户端先报超时。
GENERATION_TIMEOUT = 300

# 可自动重试的 HTTP 状态码。注意：524 是 Cloudflare 的源站读取超时，重试会再次触发
# 慢生成，并在中转站面板留下多条 524 错误记录，因此不把 524 当作可重试状态。
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def size_for(ratio: str, k: str) -> str | None:
    """由画幅与档位派生“宽x高”。长边固定为档位像素，另一边按比例取整。
    画幅为 auto 时直接返回 "auto"，交个下游模型自行决定。"""
    if ratio == "auto":
        return "auto"
    try:
        rw_str, rh_str = ratio.split(":")
        rw, rh = int(rw_str), int(rh_str)
    except (ValueError, AttributeError):
        return None
    long_edge = K_LONG_EDGE.get(k)
    if long_edge is None or rw <= 0 or rh <= 0:
        return None
    if rw >= rh:
        w, h = long_edge, round(long_edge * rh / rw)
    else:
        h, w = long_edge, round(long_edge * rw / rh)
    return f"{w}x{h}"


# 支持的全部“画幅 x 档位”组合；auto 画幅单独一项。
SIZE_COMBOS = []
for r in RATIOS:
    if r == "auto":
        SIZE_COMBOS.append({"ratio": "auto", "k": "auto", "size": "auto"})
        continue
    for k in K_LEVELS:
        s = size_for(r, k)
        if s:
            SIZE_COMBOS.append({"ratio": r, "k": k, "size": s})
VALID_SIZES = {c["size"] for c in SIZE_COMBOS}


# ---------------------------------------------------------------------------
# 配置来源：只认前端界面填写的 Base URL 与 API key。
# 后端不读 .env、不读环境变量、不内置任何提供商；两项为空时直接返回中文提示。
# ---------------------------------------------------------------------------
def resolve_api_key(override: str | None) -> str:
    """取前端传入的 API key。仅用于构建请求头，绝不写日志、绝不回传前端。"""
    return (override or "").strip()


def resolve_base_url(override: str | None) -> str:
    """取前端传入的中转站地址并规范化：去结尾斜杠，漏写协议头时按 https 补全。
    未填写时返回空串，由调用方给出提示。"""
    candidate = (override or "").strip().rstrip("/")
    if not candidate:
        return ""
    if candidate.startswith(("http://", "https://")):
        return candidate
    return f"https://{candidate}"


app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/outputs/<path:filename>")
def serve_output(filename: str):
    return send_from_directory(OUTPUT_DIR, filename)


@app.get("/api/download/<path:filename>")
def download_output(filename: str):
    """以“附件”形式下载生成图片，保证浏览器保存时使用原始文件名。
    与 /outputs 的 inline 预览路由分开，避免下载被当作图片直接打开。
    仅取 basename 做路径白名单，避免 ../ 或绝对路径目录穿越。"""
    name = Path(filename).name
    target = OUTPUT_DIR / name
    if not target.is_file():
        return jsonify({"ok": False, "error": "文件不存在或已被删除。"}), 404
    return send_from_directory(OUTPUT_DIR, name, as_attachment=True, download_name=name)


# ---------------------------------------------------------------------------
# 历史记录（持久化到 outputs/history.json，跨重启保留）
# ---------------------------------------------------------------------------
def _load_history() -> list[dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return data if isinstance(data, list) else []


def _save_history(records: list[dict[str, Any]]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_history(records: list[dict[str, Any]]) -> None:
    current = _load_history()
    current = records + current
    _save_history(current[:HISTORY_LIMIT])


@app.get("/api/history")
def history():
    return jsonify({"ok": True, "count": len(_load_history()), "items": _load_history()})


@app.delete("/api/history")
def clear_history():
    _save_history([])
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# 健康检查 / 模型校验
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            # 提供商地址与 API key 只来自前端界面，服务端不保存任何配置。
            "config_source": "ui",
            "model": DEFAULT_MODEL,
            "ratios": RATIOS,
            "k_levels": K_LEVELS,
            "sizes": SIZE_COMBOS,
            "qualities": sorted(VALID_QUALITIES),
        }
    )


@app.get("/api/models")
def models():
    """校验中转站可达性，并确认模型列表中包含 gpt-image-2。"""
    key = resolve_api_key(request.headers.get("X-Api-Key"))
    if not key:
        return jsonify({"ok": False, "error": MISSING_KEY_ERROR}), 400

    target_base = resolve_base_url(request.args.get("base_url"))
    if not target_base:
        return jsonify({"ok": False, "error": MISSING_BASE_URL_ERROR}), 400
    try:
        resp = HTTP.get(
            f"{target_base}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        return jsonify({"ok": False, "error": f"无法连接中转站：{exc.__class__.__name__}"}), 502

    if resp.status_code != 200:
        return jsonify(
            {"ok": False, "status": resp.status_code, "error": _summarize_http_error(resp)}
        ), 502

    data = resp.json()
    ids = [m.get("id", "") for m in data.get("data", [])]
    return jsonify(
        {
            "ok": True,
            "model": DEFAULT_MODEL,
            "available": DEFAULT_MODEL in ids,
            "count": len(ids),
            "models": ids,
            "base_url": target_base,
        }
    )


# ---------------------------------------------------------------------------
# 生图
# ---------------------------------------------------------------------------
@app.post("/api/generate")
def generate():
    # 无参考图时走 JSON；带参考图时前端会以 multipart/form-data 上传图片。
    has_reference = bool(request.files.getlist("image") or request.files.getlist("images"))
    payload = request.form if has_reference else (request.get_json(silent=True) or {})
    prompt = (payload.get("prompt") or "").strip()
    quality = (payload.get("quality") or "auto").strip()
    override_base = resolve_base_url(payload.get("base_url"))
    key = resolve_api_key(payload.get("api_key"))

    # 画幅与档位派生实际尺寸；auto 画幅忽略分辨率档位。
    ratio = (payload.get("ratio") or "auto").strip()
    if ratio not in RATIOS:
        return jsonify({"ok": False, "error": f"画幅 {ratio!r} 不受支持。可选：{'、'.join(RATIOS)}"}), 400
    if ratio == "auto":
        k = "auto"
        size = "auto"
    else:
        k = (payload.get("k") or "1K").strip()
        if k not in K_LEVELS:
            return jsonify({"ok": False, "error": f"分辨率 {k!r} 不受支持，最高 {K_LEVELS[-1]}。可选：{'、'.join(K_LEVELS)}"}), 400
        size = size_for(ratio, k)
        if not size:
            return jsonify({"ok": False, "error": "无法从画幅与分辨率派生尺寸。"}), 400

    # 数量：中转站多数实现支持 n>=1，默认 1。
    try:
        n = int(payload.get("n") or 1)
    except (TypeError, ValueError):
        n = 1

    if not prompt:
        return jsonify({"ok": False, "error": "prompt 不能为空。"}), 400
    if quality not in VALID_QUALITIES:
        return jsonify({"ok": False, "error": f"质量 {quality!r} 不受支持。可选：{'、'.join(sorted(VALID_QUALITIES))}"}), 400
    if n < 1 or n > 4:
        return jsonify({"ok": False, "error": "n 只能在 1 到 4 之间。"}), 400

    if not key:
        return jsonify({"ok": False, "error": MISSING_KEY_ERROR}), 400
    if not override_base:
        return jsonify({"ok": False, "error": MISSING_BASE_URL_ERROR}), 400

    # 带参考图则调用 /images/edits（multipart），否则调用 /images/generations（JSON）。
    try:
        if has_reference:
            files_args = []
            for idx, f in enumerate(request.files.getlist("image") or request.files.getlist("images")):
                filename = f.filename or f"reference-{idx + 1}.png"
                ctype = f.mimetype or "image/png"
                files_args.append(("image", (filename, f.stream, ctype)))
            resp = _post_with_retry(
                f"{override_base}/images/edits",
                headers={"Authorization": f"Bearer {key}"},
                files=files_args,
                data={
                    "model": DEFAULT_MODEL,
                    "prompt": prompt,
                    "size": size,
                    "quality": quality,
                    "n": str(n),
                },
                timeout=GENERATION_TIMEOUT,
            )
        else:
            body = {
                "model": DEFAULT_MODEL,
                "prompt": prompt,
                "size": size,
                "quality": quality,
                "n": n,
            }
            resp = _post_with_retry(
                f"{override_base}/images/generations",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=GENERATION_TIMEOUT,
            )
    except requests.RequestException as exc:
        return jsonify({"ok": False, "error": f"请求中转站失败：{exc.__class__.__name__}. 请检查代理或网络。"}), 502

    if resp.status_code != 200:
        return jsonify(
            {"ok": False, "status": resp.status_code, "error": _summarize_http_error(resp)}
        ), 502

    try:
        data = resp.json()
    except ValueError:
        return jsonify({"ok": False, "error": "中转站返回了非 JSON 响应。"}), 502

    images = data.get("data", [])
    saved = []
    try:
        for index, item in enumerate(images):
            filename = _save_image(item, size, index)
            saved.append(
                {
                    "url": f"/outputs/{filename}",
                    "filename": filename,
                    "size": size,
                    "quality": quality,
                }
            )
    except (requests.RequestException, OSError, ValueError) as exc:
        return jsonify({"ok": False, "error": f"保存生成图片失败：{exc.__class__.__name__}. 请稍后重试。"}), 502

    if not saved:
        return jsonify({"ok": False, "error": "中转站返回的 data 为空，没有生成图片。"}), 502

    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    history_records = [
        {
            "id": uuid.uuid4().hex,
            "url": img["url"],
            "filename": img["filename"],
            "prompt": prompt,
            "ratio": ratio,
            "k": k,
            "size": size,
            "quality": quality,
            "reference": bool(has_reference),
            "created_at": created_at,
        }
        for img in saved
    ]
    _append_history(history_records)

    return jsonify(
        {
            "ok": True,
            "count": len(saved),
            "images": saved,
            "meta": {
                "model": DEFAULT_MODEL,
                "size": size,
                "ratio": ratio,
                "k": k,
                "quality": quality,
                "prompt": prompt,
                "reference": bool(has_reference),
            },
        }
    )


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _validate_size(size: str) -> str | None:
    """校验尺寸必须是支持的画幅 x 档位组合之一。返回错误消息或 None。"""
    if size in VALID_SIZES:
        return None
    return f"尺寸 {size!r} 不受支持。支持的画幅为 {'、'.join(RATIOS)}，分辨率最高 {K_LEVELS[-1]}。"


def _post_with_retry(
    url: str,
    headers: dict[str, str],
    json: dict[str, Any] | None = None,
    files: Any | None = None,
    data: dict[str, str] | None = None,
    attempts: int = 3,
    timeout: int = GENERATION_TIMEOUT,
):
    """连接异常退避重试；HTTP 429 / 5xx 有限重试。总时长受控，避免长时间阻塞。"""
    for attempt in range(attempts):
        try:
            resp = HTTP.post(url, headers=headers, json=json, files=files, data=data, timeout=timeout)
        except requests.RequestException:
            # 网络或连接层异常：退避后重试，最后一次直接抛出。
            if attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise

        if resp.status_code in _RETRYABLE_STATUS and attempt < attempts - 1:
            time.sleep(2 * (attempt + 1))
            continue
        return resp
    raise RuntimeError("请求重试次数已用尽")  # pragma: no cover


def _summarize_http_error(resp: requests.Response) -> str:
    """把 4xx/5xx 转成不泄漏 key 的中文提示。"""
    status = resp.status_code
    text = resp.text.strip().lower()
    if status == 401:
        return "认证失败（401）。请检查界面里填写的 API Key 是否正确，以及 Base URL 是否指向你的中转站（不要填成官方地址）。"
    if status == 403:
        if "just a moment" in text or "cloudflare" in text:
            return "中转站被 Cloudflare/WAF 拦截（403）。请确认 Base URL 正确，或中转站是否限制了脚本访问。"
        return "无权限（403）。请确认 key 已开通图片生成权限。"
    if status == 404:
        return "接口不存在（404）。请确认界面里的 Base URL 填写完整（通常以 /v1 结尾），且该中转站已开通图片生成接口。"
    if status == 429:
        return "触发限流（429）。请稍后重试，或降低并发/数量。"
    if status == 524:
        return "中转站源站响应超时（524，Cloudflare Proxy Read Timeout）。图片生成耗时超过中转站代理窗口（约 120 秒）。请稍后重试；若常现，建议改用 auto/中/低质量或更小尺寸。"
    if status >= 500:
        return f"中转站服务异常（{status}）。请稍后重试。"
    if "invalid_api_key" in text:
        return "无效 API key（invalid_api_key）。请检查界面里填写的 key 与 Base URL 是否属于同一个中转站。"
    return f"中转站返回错误（{status}）：{resp.text[:160]}"


def _save_image(item: dict[str, Any], size: str, index: int) -> str:
    """从 b64_json 或 url 保存图片，返回文件名。"""
    b64 = item.get("b64_json")
    url = item.get("url")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"image2-{stamp}-{uuid.uuid4().hex[:8]}-{index + 1}.png"
    target = OUTPUT_DIR / filename

    if b64:
        import base64

        raw = base64.b64decode(b64)
        target.write_bytes(raw)
    elif url:
        img_resp = HTTP.get(url, timeout=120)
        img_resp.raise_for_status()
        target.write_bytes(img_resp.content)
    else:
        # 若返回的是 data URL 或纯 base64 字符串也尝试兜底。
        raw = item.get("b64", "")
        if isinstance(raw, str):
            import base64

            if raw.startswith("data:"):
                raw = raw.split(",", 1)[1]
            target.write_bytes(base64.b64decode(raw))
        else:
            raise ValueError("响应中缺少 b64_json 或 url")

    return filename


def _resolve_port(default: int = 8787) -> int:
    """端口优先级：命令行 --port 8123 > 环境变量 PORT > 默认 8787。
    打包版没有 .env，双击启动用默认端口即可，需要改端口时传参。"""
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg.startswith("--port="):
            value = arg.split("=", 1)[1]
        elif arg in ("-p", "--port") and index + 1 < len(argv):
            value = argv[index + 1]
        else:
            continue
        try:
            return int(value)
        except ValueError:
            break
    try:
        return int(os.environ.get("PORT") or default)
    except ValueError:
        return default


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=_resolve_port(), debug=False, threaded=True)
