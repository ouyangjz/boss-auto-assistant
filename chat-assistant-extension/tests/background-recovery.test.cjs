"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function loadBackground(sendMessage, executeScript = async () => undefined) {
  const injections = [];
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
        get: async () => ({}),
        set: async () => undefined
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
    }

    addEventListener() {}
    send() {}
    close() {}
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
      autoSendStorageKey: "autoSend",
      maxStoredTaskIds: 200
    };
  };

  const source = fs.readFileSync(
    path.join(__dirname, "..", "background.js"),
    "utf8"
  );
  vm.runInContext(source, context, { filename: "background.js" });
  return { context, injections };
}

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
