"use strict";

const CONFIG = globalThis.ChatAssistantConfig;
const toggle = document.getElementById("autoSendToggle");
const modeText = document.getElementById("modeText");
const warning = document.getElementById("warning");

function render(enabled) {
  toggle.checked = enabled;
  modeText.textContent = enabled ? "是，回填后自动发送" : "否，仅回填输入框";
  warning.textContent = enabled
    ? "已开启：回填并复核后，将等待 0.5～1 秒自动发送。"
    : "当前不会自动发送，回填后请人工确认。";
  warning.classList.toggle("enabled", enabled);
}

async function loadSetting() {
  const stored = await chrome.storage.local.get(CONFIG.autoSendStorageKey);
  render(stored[CONFIG.autoSendStorageKey] === true);
}

toggle.addEventListener("change", async () => {
  const enabled = toggle.checked;
  await chrome.storage.local.set({ [CONFIG.autoSendStorageKey]: enabled });
  render(enabled);
});

void loadSetting();
