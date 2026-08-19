(() => {
  const ns = globalThis.BossPlugin;
  const labels = {
    IDLE: "空闲",
    RUNNING: "运行中",
    PAUSED: "已暂停",
    WAITING_DETAIL: "等待详情",
    REQUESTING: "匹配中",
    COMMUNICATING: "沟通中",
    FINISHED: "扫描完成",
    ERROR: "错误",
    STOPPED: "已停止"
  };
  const elements = {
    status: document.querySelector("#statusBadge"),
    currentJob: document.querySelector("#currentJob"),
    scannedCount: document.querySelector("#scannedCount"),
    matchedCount: document.querySelector("#matchedCount"),
    currentScore: document.querySelector("#currentScore"),
    lastError: document.querySelector("#lastError"),
    pageHint: document.querySelector("#pageHint"),
    start: document.querySelector("#startButton"),
    pause: document.querySelector("#pauseButton"),
    stop: document.querySelector("#stopButton"),
    clearCurrent: document.querySelector("#clearCurrentButton"),
    bulkApply: document.querySelector("#bulkApplyEnabled")
  };

  function render(state = {}) {
    elements.status.textContent = labels[state.status] || state.status || "空闲";
    elements.currentJob.textContent = state.currentJob || "—";
    elements.scannedCount.textContent = state.scannedCount ?? 0;
    elements.matchedCount.textContent = state.matchedCount ?? 0;
    elements.currentScore.textContent = state.currentScore == null ? "—" : `${state.currentScore} / 100`;
    elements.lastError.textContent = state.lastError || "无";
    const active = ["RUNNING", "WAITING_DETAIL", "REQUESTING", "COMMUNICATING"].includes(state.status);
    elements.start.textContent = state.status === "PAUSED" ? "继续" : "开始";
    elements.start.disabled = active;
    elements.pause.disabled = !active;
    elements.stop.disabled = ["IDLE", "STOPPED", "FINISHED"].includes(state.status);
  }

  async function activeBossTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !/^https:\/\/www\.zhipin\.com\/web\/geek\/jobs/.test(tab.url || "")) {
      throw new Error("请先打开 BOSS 岗位搜索列表页");
    }
    return tab;
  }

  async function command(name) {
    elements.pageHint.textContent = "";
    try {
      const tab = await activeBossTab();
      const response = await chrome.tabs.sendMessage(tab.id, { type: ns.MESSAGES.CONTROL, command: name });
      if (!response?.ok) throw new Error(response?.error || "Content Script 未响应");
      render(response.state);
    } catch (error) {
      elements.pageHint.textContent = error.message.includes("Receiving end does not exist")
        ? "页面尚未注入插件，请刷新 BOSS 页面后重试"
        : error.message;
    }
  }

  async function clearCurrentInfo() {
    elements.pageHint.textContent = "";
    try {
      const tab = await activeBossTab();
      const response = await chrome.tabs.sendMessage(tab.id, {
        type: ns.MESSAGES.CONTROL,
        command: "CLEAR_CURRENT"
      });
      if (!response?.ok) throw new Error(response?.error || "Content Script 未响应");
      render(response.state);
    } catch (_error) {
      // 页面已关闭或跳转时仍清空持久化状态；下次页面注入后会从头扫描。
      const next = {
        status: "IDLE",
        currentJob: "",
        scannedCount: 0,
        matchedCount: 0,
        currentScore: null,
        lastError: "",
        updatedAt: new Date().toISOString()
      };
      await chrome.storage.local.set({
        [ns.CONFIG.storageKeys.taskState]: next,
        [ns.CONFIG.storageKeys.processedJobs]: []
      });
      render(next);
    }
  }

  elements.start.addEventListener("click", () => command("START"));
  elements.pause.addEventListener("click", () => command("PAUSE"));
  elements.stop.addEventListener("click", () => command("STOP"));
  elements.clearCurrent.addEventListener("click", clearCurrentInfo);
  elements.bulkApply.addEventListener("change", async () => {
    await chrome.storage.local.set({
      [ns.CONFIG.storageKeys.bulkApplyEnabled]: elements.bulkApply.checked
    });
  });

  chrome.storage.local.get([
    ns.CONFIG.storageKeys.taskState,
    ns.CONFIG.storageKeys.bulkApplyEnabled
  ]).then((result) => {
    render(result[ns.CONFIG.storageKeys.taskState]);
    elements.bulkApply.checked = result[ns.CONFIG.storageKeys.bulkApplyEnabled] === true;
  });
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === "local" && changes[ns.CONFIG.storageKeys.taskState]) {
      render(changes[ns.CONFIG.storageKeys.taskState].newValue);
    }
    if (areaName === "local" && changes[ns.CONFIG.storageKeys.bulkApplyEnabled]) {
      elements.bulkApply.checked = changes[ns.CONFIG.storageKeys.bulkApplyEnabled].newValue === true;
    }
  });
})();
