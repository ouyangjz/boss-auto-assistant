importScripts("../config/constants.js", "../utils/logger.js");

const { CONFIG, MESSAGES } = globalThis.BossPlugin;

chrome.runtime.onInstalled.addListener(async () => {
  const existing = await chrome.storage.local.get([
    CONFIG.storageKeys.taskState,
    CONFIG.storageKeys.bulkApplyEnabled
  ]);
  const defaults = {};
  if (!existing[CONFIG.storageKeys.taskState]) {
    defaults[CONFIG.storageKeys.taskState] = {
      status: "IDLE",
      currentJob: "",
      scannedCount: 0,
      matchedCount: 0,
      currentScore: null,
      lastError: "",
      updatedAt: new Date().toISOString()
    };
  }
  if (existing[CONFIG.storageKeys.bulkApplyEnabled] === undefined) {
    defaults[CONFIG.storageKeys.bulkApplyEnabled] = false;
  }
  if (Object.keys(defaults).length) await chrome.storage.local.set(defaults);
});

const pendingRequests = new Map();

async function evaluateJob(payload, requestId) {
  const controller = new AbortController();
  pendingRequests.set(requestId, controller);
  const timeout = setTimeout(() => controller.abort(), CONFIG.requestTimeoutMs);
  try {
    const stored = await chrome.storage.local.get(CONFIG.storageKeys.bulkApplyEnabled);
    const bulkApplyEnabled = stored[CONFIG.storageKeys.bulkApplyEnabled] === true;
    const apiUrl = bulkApplyEnabled ? CONFIG.bulkApiUrl : CONFIG.apiUrl;
    const response = await fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    if (!response.ok) {
      const body = await response.text();
      return { ok: false, code: "API_HTTP_ERROR", error: `FastAPI HTTP ${response.status}: ${body}` };
    }
    return { ok: true, data: await response.json() };
  } catch (error) {
    if (error?.name === "AbortError") {
      return {
        ok: false,
        code: "API_TIMEOUT",
        error: `FastAPI 请求超过 ${Math.round(CONFIG.requestTimeoutMs / 1000)} 秒`
      };
    }
    return { ok: false, code: "API_UNAVAILABLE", error: error?.message || "无法连接 FastAPI" };
  } finally {
    clearTimeout(timeout);
    pendingRequests.delete(requestId);
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === MESSAGES.CANCEL_EVALUATION) {
    pendingRequests.get(message.requestId)?.abort();
    sendResponse({ ok: true });
    return false;
  }
  if (message?.type === MESSAGES.EVALUATE_JOB) {
    evaluateJob(message.payload, message.requestId).then(sendResponse);
    return true;
  }
  return false;
});
