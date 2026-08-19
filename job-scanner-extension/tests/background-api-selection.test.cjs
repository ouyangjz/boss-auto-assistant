const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const backgroundSource = fs.readFileSync(
  path.join(__dirname, "..", "background", "background.js"),
  "utf8"
);

async function evaluateWithBulkMode(bulkApplyEnabled) {
  let messageListener;
  let requestedUrl;
  const config = {
    apiUrl: "http://127.0.0.1:8000/api/v1/jobs/evaluate",
    bulkApiUrl: "http://127.0.0.1:8000/api/v1/jobs/bulk-evaluate",
    requestTimeoutMs: 1000,
    storageKeys: {
      taskState: "taskState",
      bulkApplyEnabled: "bulkApplyEnabled"
    }
  };
  const context = vm.createContext({
    AbortController,
    clearTimeout,
    console,
    importScripts() {},
    setTimeout,
    fetch: async (url) => {
      requestedUrl = url;
      return {
        ok: true,
        async json() {
          return { success: true, match_score: bulkApplyEnabled ? 71 : 80 };
        }
      };
    },
    BossPlugin: {
      CONFIG: config,
      MESSAGES: {
        EVALUATE_JOB: "evaluate",
        CANCEL_EVALUATION: "cancel"
      }
    },
    chrome: {
      runtime: {
        onInstalled: { addListener() {} },
        onMessage: {
          addListener(listener) {
            messageListener = listener;
          }
        }
      },
      storage: {
        local: {
          async get() {
            return { [config.storageKeys.bulkApplyEnabled]: bulkApplyEnabled };
          },
          async set() {}
        }
      }
    }
  });
  context.globalThis = context;
  vm.runInContext(backgroundSource, context);

  const response = await new Promise((resolve) => {
    const asyncResponse = messageListener(
      { type: "evaluate", requestId: "request-1", payload: { job_id: "job-1" } },
      {},
      resolve
    );
    assert.equal(asyncResponse, true);
  });
  assert.equal(response.ok, true);
  return requestedUrl;
}

test("uses the regular evaluation endpoint when bulk apply is disabled", async () => {
  assert.equal(
    await evaluateWithBulkMode(false),
    "http://127.0.0.1:8000/api/v1/jobs/evaluate"
  );
});

test("uses the bulk evaluation endpoint when bulk apply is enabled", async () => {
  assert.equal(
    await evaluateWithBulkMode(true),
    "http://127.0.0.1:8000/api/v1/jobs/bulk-evaluate"
  );
});
