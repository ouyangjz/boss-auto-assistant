"use strict";

importScripts("config.js");

const CONFIG = globalThis.ChatAssistantConfig;
let socket = null;
let reconnectAttempt = 0;
let reconnectTimer = null;
let heartbeatTimer = null;
let connectionEnabled = false;
const inFlightTaskIds = new Set();
const contentInjectionByTabId = new Map();

function log(scope, message, ...details) {
  console.log(`[ChatAssistant][${scope}] ${message}`, ...details);
}

function scheduleReconnect() {
  if (!connectionEnabled || reconnectTimer) return;
  const index = Math.min(reconnectAttempt, CONFIG.reconnectDelaysMs.length - 1);
  const delay = CONFIG.reconnectDelaysMs[index];
  reconnectAttempt += 1;
  log("WS", `reconnecting in ${delay}ms...`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (connectionEnabled) connectWebSocket();
  }, delay);
}

function cancelReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = null;
  reconnectAttempt = 0;
}

function stopHeartbeat() {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  heartbeatTimer = null;
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (connectionEnabled && socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "ping" }));
    }
  }, CONFIG.heartbeatIntervalMs);
}

function disconnectWebSocket() {
  cancelReconnect();
  stopHeartbeat();
  const activeSocket = socket;
  socket = null;
  if (activeSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(activeSocket.readyState)) {
    activeSocket.close();
  }
  log("WS", "connection disabled");
}

function setConnectionEnabled(enabled) {
  const next = enabled === true;
  if (connectionEnabled === next) {
    if (next) connectWebSocket();
    return;
  }
  connectionEnabled = next;
  if (connectionEnabled) {
    log("WS", "connection enabled");
    connectWebSocket();
  } else {
    disconnectWebSocket();
  }
}

async function syncConnectionPreference() {
  const stored = await chrome.storage.local.get(CONFIG.connectionEnabledStorageKey);
  setConnectionEnabled(stored[CONFIG.connectionEnabledStorageKey] === true);
}

async function getFilledTaskIds() {
  const stored = await chrome.storage.local.get(CONFIG.processedTaskStorageKey);
  return Array.isArray(stored[CONFIG.processedTaskStorageKey])
    ? stored[CONFIG.processedTaskStorageKey]
    : [];
}

async function rememberFilledTask(taskId) {
  const taskIds = await getFilledTaskIds();
  const next = [...taskIds.filter((item) => item !== taskId), taskId]
    .slice(-CONFIG.maxStoredTaskIds);
  await chrome.storage.local.set({ [CONFIG.processedTaskStorageKey]: next });
}

async function getAutoSendEnabled() {
  const stored = await chrome.storage.local.get(CONFIG.autoSendStorageKey);
  return stored[CONFIG.autoSendStorageKey] === true;
}

function sendAck(taskId, status) {
  if (socket?.readyState !== WebSocket.OPEN) {
    log("WS", `ACK deferred by disconnection task=${taskId} status=${status}`);
    return false;
  }
  socket.send(JSON.stringify({ type: "ack", task_id: taskId, status }));
  log("Task", `ACK task=${taskId} status=${status}`);
  return true;
}

async function findChatTab() {
  const tabs = await chrome.tabs.query({ url: "https://www.zhipin.com/web/geek/chat*" });
  return tabs.sort((left, right) => Number(Boolean(right.active)) - Number(Boolean(left.active)))[0] || null;
}

function isMissingMessageReceiver(error) {
  const message = String(error?.message || error || "");
  return /Receiving end does not exist|Could not establish connection/i.test(message);
}

async function ensureContentScript(tabId) {
  const existingInjection = contentInjectionByTabId.get(tabId);
  if (existingInjection) return existingInjection;

  const injection = chrome.scripting.executeScript({
    target: { tabId },
    files: ["config.js", "content.js"]
  }).then(() => {
    log("Content", `injected into tab=${tabId}`);
  }).finally(() => {
    contentInjectionByTabId.delete(tabId);
  });
  contentInjectionByTabId.set(tabId, injection);
  return injection;
}

async function sendIntroductionToTab(tabId, payload) {
  try {
    return await chrome.tabs.sendMessage(tabId, {
      type: CONFIG.messageType,
      payload
    });
  } catch (error) {
    if (!isMissingMessageReceiver(error)) throw error;
    log("Content", `receiver missing in tab=${tabId}; injecting and retrying`);
    await ensureContentScript(tabId);
    return chrome.tabs.sendMessage(tabId, {
      type: CONFIG.messageType,
      payload
    });
  }
}

async function handleIntroductionTask(task) {
  const taskId = String(task.task_id || "").trim();
  if (!taskId || inFlightTaskIds.has(taskId)) return;

  const filledTaskIds = await getFilledTaskIds();
  if (filledTaskIds.includes(taskId)) {
    log("Task", `already filled task=${taskId}`);
    sendAck(taskId, "filled");
    return;
  }

  inFlightTaskIds.add(taskId);
  try {
    log("WS", `introduction_ready task=${taskId}`);
    const tab = await findChatTab();
    if (!tab?.id) {
      log("Candidate", "BOSS chat page not found");
      sendAck(taskId, "candidate_not_found");
      return;
    }

    let result;
    try {
      const autoSendEnabled = await getAutoSendEnabled();
      log("Task", `auto_send=${autoSendEnabled ? "yes" : "no"} task=${taskId}`);
      result = await sendIntroductionToTab(tab.id, {
        ...task,
        auto_send: autoSendEnabled
      });
    } catch (error) {
      log("Task", "content script unavailable", error?.message || error);
      sendAck(taskId, "content_script_unavailable");
      return;
    }

    const taskStatus = result?.status || "input_not_found";
    log(
      "Task",
      `content result task=${taskId} status=${taskStatus} ` +
        `selection_mode=${result?.selection_mode || "unknown"} ` +
        `click_attempt=${result?.click_attempt ?? "unknown"}`
    );
    if (["filled", "sent", "send_unverified"].includes(taskStatus)) {
      await rememberFilledTask(taskId);
    }
    sendAck(taskId, taskStatus);
  } catch (error) {
    log("Task", `failed task=${taskId}`, error);
    sendAck(taskId, "input_not_found");
  } finally {
    inFlightTaskIds.delete(taskId);
  }
}

function connectWebSocket() {
  if (!connectionEnabled) return;
  if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) return;

  let currentSocket;
  try {
    currentSocket = new WebSocket(CONFIG.websocketUrl);
    socket = currentSocket;
  } catch (error) {
    log("WS", "connection creation failed", error);
    scheduleReconnect();
    return;
  }

  currentSocket.addEventListener("open", () => {
    if (!connectionEnabled || socket !== currentSocket) {
      currentSocket.close();
      return;
    }
    reconnectAttempt = 0;
    log("WS", "connected");
    startHeartbeat();
  });

  currentSocket.addEventListener("message", (event) => {
    if (!connectionEnabled || socket !== currentSocket) return;
    try {
      const message = JSON.parse(event.data);
      if (message.type === "introduction_ready") void handleIntroductionTask(message);
    } catch (error) {
      log("WS", "invalid server message", error);
    }
  });

  currentSocket.addEventListener("close", () => {
    log("WS", "disconnected");
    if (socket === currentSocket) {
      stopHeartbeat();
      socket = null;
      scheduleReconnect();
    }
  });

  currentSocket.addEventListener("error", () => {
    log("WS", "connection error");
    currentSocket.close();
  });
}

chrome.runtime.onInstalled.addListener(async () => {
  const stored = await chrome.storage.local.get([
    CONFIG.connectionEnabledStorageKey,
    CONFIG.autoSendStorageKey
  ]);
  const defaults = {};
  if (typeof stored[CONFIG.connectionEnabledStorageKey] !== "boolean") {
    defaults[CONFIG.connectionEnabledStorageKey] = false;
  }
  if (typeof stored[CONFIG.autoSendStorageKey] !== "boolean") {
    defaults[CONFIG.autoSendStorageKey] = false;
  }
  if (Object.keys(defaults).length) await chrome.storage.local.set(defaults);
  await syncConnectionPreference();
});
chrome.runtime.onStartup.addListener(() => {
  void syncConnectionPreference();
});
chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local" || !changes[CONFIG.connectionEnabledStorageKey]) return;
  setConnectionEnabled(changes[CONFIG.connectionEnabledStorageKey].newValue === true);
});
void syncConnectionPreference();
