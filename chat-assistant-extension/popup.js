"use strict";

const CONFIG = globalThis.ChatAssistantConfig;
const connectionToggle = document.getElementById("connectionToggle");
const connectionModeText = document.getElementById("connectionModeText");
const connectionHint = document.getElementById("connectionHint");
const autoSendToggle = document.getElementById("autoSendToggle");
const modeText = document.getElementById("modeText");
const warning = document.getElementById("warning");

function renderConnection(enabled) {
  connectionToggle.checked = enabled;
  connectionModeText.textContent = enabled
    ? "是，建立 WebSocket 连接"
    : "否，不建立 WebSocket 连接";
  connectionHint.textContent = enabled
    ? "已允许连接本地服务；后端未启动时会按间隔自动重连。"
    : "本地服务连接已关闭，插件不会尝试建立连接。";
  connectionHint.classList.toggle("enabled", enabled);
}

function renderAutoSend(enabled) {
  autoSendToggle.checked = enabled;
  modeText.textContent = enabled ? "是，回填后自动发送" : "否，仅回填输入框";
  warning.textContent = enabled
    ? "已开启：回填并复核后，将等待 0.5～1 秒自动发送。"
    : "当前不会自动发送，回填后请人工确认。";
  warning.classList.toggle("enabled", enabled);
}

async function loadSetting() {
  const stored = await chrome.storage.local.get([
    CONFIG.connectionEnabledStorageKey,
    CONFIG.autoSendStorageKey
  ]);
  renderConnection(stored[CONFIG.connectionEnabledStorageKey] === true);
  renderAutoSend(stored[CONFIG.autoSendStorageKey] === true);
}

connectionToggle.addEventListener("change", async () => {
  const enabled = connectionToggle.checked;
  await chrome.storage.local.set({ [CONFIG.connectionEnabledStorageKey]: enabled });
  renderConnection(enabled);
});

autoSendToggle.addEventListener("change", async () => {
  const enabled = autoSendToggle.checked;
  await chrome.storage.local.set({ [CONFIG.autoSendStorageKey]: enabled });
  renderAutoSend(enabled);
});

void loadSetting();
