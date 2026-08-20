"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function loadBackground(
  sendMessage,
  executeScript = async () => undefined,
  initialStorage = {}
) {
  const injections = [];
  const webSockets = [];
  const storageValues = { ...initialStorage };
  let storageChangeListener;
  const chrome = {
    tabs: {
      query: async () => [],
      sendMessage
    },
    scripting: {
      executeScript: async (details) => {
        injections.push(details);
        await executeScript(details);
      }
    },
    storage: {
      local: {
        get: async () => ({ ...storageValues }),
        set: async (values) => Object.assign(storageValues, values)
      },
      onChanged: {
        addListener(listener) {
          storageChangeListener = listener;
        }
      }
    },
    runtime: {
      onInstalled: { addListener: () => undefined },
      onStartup: { addListener: () => undefined }
    }
  };

  class FakeWebSocket {
    static OPEN = 1;
    static CONNECTING = 0;

    constructor() {
      this.readyState = FakeWebSocket.CONNECTING;
      this.closed = false;
      this.listeners = new Map();
      webSockets.push(this);
    }

    addEventListener(type, listener) {
      this.listeners.set(type, listener);
    }
    send() {}
    close() {
      if (this.closed) return;
      this.closed = true;
      this.readyState = 3;
      this.listeners.get("close")?.();
    }
  }

  const context = vm.createContext({
    chrome,
    console,
    WebSocket: FakeWebSocket,
    clearInterval,
    clearTimeout,
    setInterval: () => 0,
    setTimeout
  });
  context.importScripts = () => {
    context.ChatAssistantConfig = {
      websocketUrl: "ws://127.0.0.1:8000/ws/chat-assistant-extension",
      messageType: "CHAT_ASSISTANT_INTRODUCTION_READY",
      reconnectDelaysMs: [1000],
      heartbeatIntervalMs: 20000,
      processedTaskStorageKey: "processed",
      connectionEnabledStorageKey: "connectionEnabled",
      autoSendStorageKey: "autoSend",
      maxStoredTaskIds: 200
    };
  };

  const source = fs.readFileSync(
    path.join(__dirname, "..", "background.js"),
    "utf8"
  );
  vm.runInContext(source, context, { filename: "background.js" });
  return {
    context,
    injections,
    webSockets,
    setConnectionEnabled(enabled) {
      const oldValue = storageValues.connectionEnabled;
      storageValues.connectionEnabled = enabled;
      storageChangeListener?.(
        { connectionEnabled: { oldValue, newValue: enabled } },
        "local"
      );
    }
  };
}

test("does not create a WebSocket while connection is disabled by default", async () => {
  const { webSockets } = loadBackground(async () => undefined);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(webSockets.length, 0);
});

test("restores an enabled connection preference when the worker starts", async () => {
  const { webSockets } = loadBackground(
    async () => undefined,
    undefined,
    { connectionEnabled: true }
  );
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(webSockets.length, 1);
});

test("connects only after enabling and disconnects when disabled", async () => {
  const background = loadBackground(async () => undefined);
  await new Promise((resolve) => setImmediate(resolve));

  background.setConnectionEnabled(true);
  assert.equal(background.webSockets.length, 1);
  assert.equal(background.webSockets[0].closed, false);

  background.setConnectionEnabled(false);
  assert.equal(background.webSockets[0].closed, true);
});

test("injects content scripts and retries when the receiver is missing", async () => {
  let attempts = 0;
  const { context, injections } = loadBackground(async () => {
    attempts += 1;
    if (attempts === 1) {
      throw new Error(
        "Could not establish connection. Receiving end does not exist."
      );
    }
    return { status: "filled" };
  });

  const result = await vm.runInContext(
    "sendIntroductionToTab(42, { task_id: 'task-1' })",
    context
  );

  assert.deepEqual(result, { status: "filled" });
  assert.equal(attempts, 2);
  assert.deepEqual(JSON.parse(JSON.stringify(injections)), [
    {
      target: { tabId: 42 },
      files: ["config.js", "content.js"]
    }
  ]);
});

test("concurrent tasks share one content-script injection", async () => {
  const attempts = new Map();
  let releaseInjection;
  const injectionGate = new Promise((resolve) => {
    releaseInjection = resolve;
  });
  const { context, injections } = loadBackground(
    async (_tabId, message) => {
      const taskId = message.payload.task_id;
      const count = (attempts.get(taskId) || 0) + 1;
      attempts.set(taskId, count);
      if (count === 1) {
        throw new Error(
          "Could not establish connection. Receiving end does not exist."
        );
      }
      return { status: "filled" };
    },
    async () => injectionGate
  );

  const pending = vm.runInContext(
    "Promise.all([" +
      "sendIntroductionToTab(42, { task_id: 'task-a' })," +
      "sendIntroductionToTab(42, { task_id: 'task-b' })" +
    "])",
    context
  );
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(injections.length, 1);
  releaseInjection();
  const results = await pending;

  assert.deepEqual(JSON.parse(JSON.stringify(results)), [
    { status: "filled" },
    { status: "filled" }
  ]);
  assert.equal(attempts.get("task-a"), 2);
  assert.equal(attempts.get("task-b"), 2);
});
