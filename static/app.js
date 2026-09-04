// 兜底画幅与档位；正式数据由 /api/health 的 ratios / k_levels 提供。
const FALLBACK_RATIOS = ["auto", "1:1", "4:3", "3:4", "16:9", "9:16"];
const FALLBACK_K_LEVELS = ["1K", "1.5K", "2K"];

const els = {
  statusChip: document.getElementById("statusChip"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  promptBox: document.getElementById("promptBox"),
  clearPromptBtn: document.getElementById("clearPromptBtn"),
  referenceInput: document.getElementById("referenceInput"),
  referencePreview: document.getElementById("referencePreview"),
  clearReferenceBtn: document.getElementById("clearReferenceBtn"),
  ratioSelect: document.getElementById("ratioSelect"),
  kSelect: document.getElementById("kSelect"),
  qualitySelect: document.getElementById("qualitySelect"),
  countInput: document.getElementById("countInput"),
  apiKeyInput: document.getElementById("apiKeyInput"),
  keyToggle: document.getElementById("keyToggle"),
  baseUrlInput: document.getElementById("baseUrlInput"),
  generateBtn: document.getElementById("generateBtn"),
  generateLabel: document.getElementById("generateLabel"),
  proxyHint: document.getElementById("proxyHint"),
  outputCount: document.getElementById("outputCount"),
  resultState: document.getElementById("resultState"),
  loading: document.getElementById("loading"),
  loadingText: document.getElementById("loadingText"),
  imageGrid: document.getElementById("imageGrid"),
  historyPanel: document.getElementById("historyPanel"),
  historyGrid: document.getElementById("historyGrid"),
  historyCount: document.getElementById("historyCount"),
  clearHistoryBtn: document.getElementById("clearHistoryBtn"),
  lightbox: document.getElementById("lightbox"),
  lightboxImg: document.getElementById("lightboxImg"),
  lightboxClose: document.getElementById("lightboxClose"),
};

let busy = false;
let validating = false;
// 提供商地址与 API key 只在界面填写、只存在本机浏览器 localStorage，
// 后端不保存任何配置，因此“是否已配置”完全由这两个输入框决定。
let referenceFiles = [];

function fillSelect(select, options) {
  select.innerHTML = "";
  for (const value of options) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value;
    select.appendChild(opt);
  }
}

function ratioLabel(value) {
  return value === "auto" ? "auto · 自动" : value;
}

function fillRatioSelect(options) {
  els.ratioSelect.innerHTML = "";
  for (const value of options) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = ratioLabel(value);
    els.ratioSelect.appendChild(opt);
  }
}

function populateSizeControls(ratios, kLevels) {
  fillRatioSelect(ratios && ratios.length ? ratios : FALLBACK_RATIOS);
  fillSelect(els.kSelect, kLevels && kLevels.length ? kLevels : FALLBACK_K_LEVELS);
  syncResolutionControl();
}

function syncResolutionControl() {
  const auto = els.ratioSelect.value === "auto";
  els.kSelect.disabled = auto;
}

function readRatio() {
  return els.ratioSelect.value;
}

function readK() {
  return els.kSelect.value;
}

function readApiKey() {
  return els.apiKeyInput.value.trim();
}

function readBaseUrl() {
  return els.baseUrlInput.value.trim();
}

function isReady() {
  return Boolean(readApiKey() && readBaseUrl());
}

// 校验中/生成中不要覆盖状态灯文案，只在空闲时刷新配置提示。
function refreshStatus() {
  if (busy || validating) return;
  if (isReady()) setStatus("", "已就绪，可开始生成");
  else setStatus("warn", "待配置：请填写 API Key 与提供商地址");
}

function loadBaseUrl() {
  return localStorage.getItem("img2_base_url") || "";
}

function saveBaseUrl(value) {
  const trimmed = (value || "").trim();
  if (trimmed) localStorage.setItem("img2_base_url", trimmed);
  else localStorage.removeItem("img2_base_url");
}

function loadApiKey() {
  return localStorage.getItem("img2_api_key") || "";
}

function saveApiKey(value) {
  const trimmed = (value || "").trim();
  if (trimmed) localStorage.setItem("img2_api_key", trimmed);
  else localStorage.removeItem("img2_api_key");
}

function setStatus(kind, text) {
  els.statusChip.className = "status-chip";
  if (kind) els.statusChip.classList.add(kind);
  els.statusText.textContent = text;
}

function sanitizeSVG(html) {
  // 只为可控图标，不做外部 HTML 注入。
  return html;
}

const ICON_DOWNLOAD = `<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12M7 11l5 5 5-5M5 21h14"></path></svg>`;
const ICON_ZOOM = `<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"></circle><path d="M21 21l-4.3-4.3M11 8v6M8 11h6"></path></svg>`;

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    populateSizeControls(data.ratios, data.k_levels);
    refreshStatus();
  } catch {
    setStatus("err", "后端未启动");
  }
}

async function checkModels() {
  if (!isReady()) {
    refreshStatus();
    return;
  }
  validating = true;
  setStatus("warn", "正在校验模型…");
  const qs = `?base_url=${encodeURIComponent(readBaseUrl())}`;
  const headers = { "X-Api-Key": readApiKey() };
  try {
    const res = await fetch(`/api/models${qs}`, { headers });
    const data = await res.json();
    if (data.ok && data.available) {
      setStatus("ok", `模型可用 (${data.model})`);
    } else if (data.ok) {
      setStatus("warn", `模型 ${data.model} 未在上游模型列表中`);
    } else {
      setStatus("err", data.error || "模型校验失败");
    }
  } catch {
    setStatus("err", "模型校验失败");
  } finally {
    validating = false;
  }
}

function setGenerateEnabled(enabled) {
  els.generateBtn.disabled = !enabled || busy;
}

function setBusy(value, label) {
  busy = value;
  els.generateBtn.disabled = busy;
  els.generateLabel.textContent = value ? label : "开始生成";
}

function showResultState() {
  els.resultState.hidden = false;
}

function hideResultState() {
  els.resultState.hidden = true;
}

function clearGrid() {
  els.imageGrid.innerHTML = "";
  els.outputCount.textContent = "";
}

function addCard(url, meta) {
  const card = document.createElement("div");
  card.className = "card";

  const img = document.createElement("img");
  img.src = url;
  img.alt = meta.prompt || "生成图片";
  img.loading = "lazy";
  img.addEventListener("click", () => openLightbox(url));

  const foot = document.createElement("div");
  foot.className = "card-foot";

  const metaEl = document.createElement("span");
  metaEl.className = "card-meta";
  metaEl.textContent = `${meta.ratio || meta.size} · ${meta.k || ""} ${meta.quality}`.trim();

  const dl = document.createElement("button");
  dl.className = "icon-btn";
  dl.title = "下载图片";
  dl.setAttribute("aria-label", "下载图片");
  dl.innerHTML = ICON_DOWNLOAD;
  dl.addEventListener("click", () => download(meta.filename));

  foot.appendChild(metaEl);
  foot.appendChild(dl);
  card.appendChild(img);
  card.appendChild(foot);
  els.imageGrid.appendChild(card);
}

function formatHistoryTime(value) {
  // 记录形如 "YYYY-MM-DD HH:MM:SS"，只展示到分钟更耐看。
  if (!value) return "";
  const m = String(value).match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/);
  return m ? `${m[1]} ${m[2]}` : String(value);
}

function formatHistoryMeta(item) {
  const ratio = item.ratio || item.size || "auto";
  const ratioText = ratio === "auto" ? "自动" : ratio;
  const k = item.k && item.k !== "auto" ? item.k : "";
  const quality = item.quality || "auto";
  const qualityText = quality === "auto" ? "自动" : quality;
  return [ratioText, k, qualityText].filter(Boolean).join(" · ");
}

function buildHistoryCard(item) {
  const card = document.createElement("article");
  card.className = "history-card";

  const imgWrap = document.createElement("div");
  imgWrap.className = "history-img-wrap";
  const img = document.createElement("img");
  img.className = "history-img";
  img.src = item.url;
  img.alt = item.prompt || "历史图片";
  img.loading = "lazy";
  img.addEventListener("click", () => openLightbox(item.url));
  imgWrap.appendChild(img);

  const zoom = document.createElement("button");
  zoom.className = "history-zoom";
  zoom.type = "button";
  zoom.title = "放大查看";
  zoom.setAttribute("aria-label", "放大查看");
  zoom.innerHTML = ICON_ZOOM;
  zoom.addEventListener("click", () => openLightbox(item.url));
  imgWrap.appendChild(zoom);

  const info = document.createElement("div");
  info.className = "history-info";

  const promptEl = document.createElement("p");
  promptEl.className = "history-prompt";
  promptEl.textContent = item.prompt || "（无提示词）";
  promptEl.title = item.prompt || "";
  info.appendChild(promptEl);

  const metaEl = document.createElement("div");
  metaEl.className = "history-meta";
  const meta = document.createElement("span");
  meta.className = "history-meta-text";
  meta.textContent = formatHistoryMeta(item);
  metaEl.appendChild(meta);

  if (item.reference) {
    const badge = document.createElement("span");
    badge.className = "history-badge";
    badge.textContent = "参考图";
    badge.title = "本次生图使用了参考图";
    metaEl.appendChild(badge);
  }

  const time = document.createElement("span");
  time.className = "history-time";
  time.textContent = formatHistoryTime(item.created_at);
  metaEl.appendChild(time);
  info.appendChild(metaEl);

  const actions = document.createElement("div");
  actions.className = "history-actions";
  const dl = document.createElement("button");
  dl.className = "icon-btn";
  dl.type = "button";
  dl.title = "下载图片";
  dl.setAttribute("aria-label", "下载图片");
  dl.innerHTML = ICON_DOWNLOAD;
  dl.addEventListener("click", () => download(item.filename));
  actions.appendChild(dl);
  info.appendChild(actions);

  card.appendChild(imgWrap);
  card.appendChild(info);
  return card;
}

function renderHistoryItems(items) {
  els.historyGrid.innerHTML = "";
  if (!items || !items.length) {
    els.historyPanel.hidden = true;
    els.historyCount.textContent = "";
    return;
  }
  for (const item of items) {
    els.historyGrid.appendChild(buildHistoryCard(item));
  }
  els.historyCount.textContent = `· ${items.length}`;
  els.historyPanel.hidden = false;
}

async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    renderHistoryItems(data.items || []);
  } catch {
    els.historyPanel.hidden = true;
  }
}

function updateReferencePreview() {
  referenceFiles = Array.from(els.referenceInput.files || []);
  els.referencePreview.innerHTML = "";
  els.referencePreview.hidden = referenceFiles.length === 0;
  els.clearReferenceBtn.hidden = referenceFiles.length === 0;
  for (const f of referenceFiles) {
    const img = document.createElement("img");
    img.className = "reference-thumb";
    img.src = URL.createObjectURL(f);
    img.alt = f.name || "参考图";
    img.title = f.name || f.type || "参考图";
    els.referencePreview.appendChild(img);
  }
}

function clearReference() {
  els.referenceInput.value = "";
  referenceFiles = [];
  els.referencePreview.innerHTML = "";
  els.referencePreview.hidden = true;
  els.clearReferenceBtn.hidden = true;
}

function download(filename) {
  const a = document.createElement("a");
  a.href = `/api/download/${encodeURIComponent(filename || "image.png")}`;
  a.download = filename || "image.png";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function openLightbox(url) {
  els.lightboxImg.src = url;
  els.lightbox.hidden = false;
}

function closeLightbox() {
  els.lightbox.hidden = true;
  els.lightboxImg.src = "";
}

function showError(message) {
  const existing = els.imageGrid.previousElementSibling;
  if (existing && existing.classList.contains("error")) existing.remove();
  const box = document.createElement("div");
  box.className = "error";
  box.textContent = message;
  els.imageGrid.parentNode.insertBefore(box, els.imageGrid);
}

function clearError() {
  const existing = els.imageGrid.previousElementSibling;
  if (existing && existing.classList.contains("error")) existing.remove();
}

async function generate() {
  const prompt = els.promptBox.value.trim();
  const baseUrl = readBaseUrl();
  const apiKey = readApiKey();
  if (!prompt) {
    els.promptBox.focus();
    showError("请先输入提示词。");
    return;
  }
  // 程序不内置中转站，缺任何一项都无法调用，先在前端拦下并聚焦到对应输入框。
  if (!apiKey) {
    els.apiKeyInput.focus();
    showError("请先填写 API Key。");
    return;
  }
  if (!baseUrl) {
    els.baseUrlInput.focus();
    showError("请先填写提供商地址（Base URL），例如 https://你的中转站地址/v1。");
    return;
  }

  clearError();
  hideResultState();
  clearGrid();
  setBusy(true, "正在生成…");
  els.loading.hidden = false;
  els.loadingText.textContent = "正在生成，通常需要 20 秒~2 分钟，请耐心等待…";

  const hasRef = referenceFiles.length > 0;

  let headers;
  let body;
  if (hasRef) {
    const fd = new FormData();
    fd.append("prompt", prompt);
    fd.append("ratio", readRatio());
    fd.append("k", readK());
    fd.append("quality", els.qualitySelect.value);
    fd.append("n", String(parseInt(els.countInput.value, 10) || 1));
    if (baseUrl) fd.append("base_url", baseUrl);
    if (apiKey) fd.append("api_key", apiKey);
    for (const f of referenceFiles) fd.append("image", f);
    body = fd;
  } else {
    const payload = {
      prompt,
      ratio: readRatio(),
      k: readK(),
      quality: els.qualitySelect.value,
      n: parseInt(els.countInput.value, 10) || 1,
    };
    if (baseUrl) payload.base_url = baseUrl;
    if (apiKey) payload.api_key = apiKey;
    headers = { "Content-Type": "application/json" };
    body = JSON.stringify(payload);
  }

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers,
      body,
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || `生成失败（HTTP ${res.status}）`);
    }

    els.outputCount.textContent = `本次 ${data.count} 张`;
    for (const img of data.images) {
      addCard(img.url, { filename: img.filename, ratio: data.meta.ratio, k: data.meta.k, size: img.size, quality: img.quality, prompt: data.meta.prompt });
    }
    clearReference();
    loadHistory();
  } catch (err) {
    showResultState();
    showError(err.message || "生成失败，请稍后重试。");
  } finally {
    els.loading.hidden = true;
    setBusy(false, "再次生成");
  }
}

function bindEvents() {
  els.generateBtn.addEventListener("click", generate);
  els.clearPromptBtn.addEventListener("click", () => {
    els.promptBox.value = "";
    els.promptBox.focus();
  });

  for (const btn of document.querySelectorAll(".step-btn")) {
    btn.addEventListener("click", () => {
      const delta = parseInt(btn.dataset.step, 10);
      let v = parseInt(els.countInput.value, 10) || 1;
      v = Math.max(1, Math.min(4, v + delta));
      els.countInput.value = v;
    });
  }

  els.countInput.addEventListener("change", () => {
    let v = parseInt(els.countInput.value, 10) || 1;
    v = Math.max(1, Math.min(4, v));
    els.countInput.value = v;
  });

  // 画幅 / 分辨率切换即保存并重新校验模型。
  els.ratioSelect.addEventListener("change", () => {
    syncResolutionControl();
    if (isReady()) checkModels();
  });
  els.kSelect.addEventListener("change", () => {
    if (isReady()) checkModels();
  });

  els.referenceInput.addEventListener("change", updateReferencePreview);
  els.clearReferenceBtn.addEventListener("click", clearReference);

  // API Key：显示/隐藏、本地保存
  els.keyToggle.addEventListener("click", () => {
    const show = els.apiKeyInput.type === "password";
    els.apiKeyInput.type = show ? "text" : "password";
    els.keyToggle.setAttribute("aria-label", show ? "隐藏 API Key" : "显示/隐藏 API Key");
  });
  els.apiKeyInput.addEventListener("input", () => {
    saveApiKey(els.apiKeyInput.value);
    refreshStatus();
  });
  els.apiKeyInput.addEventListener("change", () => {
    if (isReady()) checkModels();
    else refreshStatus();
  });
  els.apiKeyInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (isReady()) checkModels();
      else refreshStatus();
    }
  });

  // API Base URL：本地保存 + 变更时重新校验模型
  els.baseUrlInput.addEventListener("input", () => {
    saveBaseUrl(els.baseUrlInput.value);
    refreshStatus();
  });
  els.baseUrlInput.addEventListener("change", () => {
    if (isReady()) checkModels();
    else refreshStatus();
  });
  els.baseUrlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (isReady()) checkModels();
      else refreshStatus();
    }
  });

  els.lightboxClose.addEventListener("click", closeLightbox);
  els.lightbox.addEventListener("click", (e) => {
    if (e.target === els.lightbox) closeLightbox();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeLightbox();
  });

  els.clearHistoryBtn.addEventListener("click", async () => {
    if (!window.confirm("确定清空全部历史记录？此操作只会移除列表记录，不会删除 outputs/generated 中已生成的图片文件。")) return;
    try {
      const res = await fetch("/api/history", { method: "DELETE" });
      if (res.ok) {
        els.historyCount.textContent = "";
      }
    } catch {}
    loadHistory();
  });

  els.promptBox.addEventListener("input", () => {
    if (els.promptBox.value.trim()) setGenerateEnabled(true);
  });

  els.promptBox.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") generate();
  });
}

function init() {
  populateSizeControls();
  els.apiKeyInput.value = loadApiKey();
  els.baseUrlInput.value = loadBaseUrl();
  bindEvents();
  loadHistory();
  checkHealth().then(() => {
    if (isReady()) checkModels();
  });
}

init();
