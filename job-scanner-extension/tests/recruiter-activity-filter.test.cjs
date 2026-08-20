const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const extractorSource = fs.readFileSync(
  path.join(__dirname, "..", "content", "job-extractor.js"),
  "utf8"
);
const scannerSource = fs.readFileSync(
  path.join(__dirname, "..", "content", "scanner.js"),
  "utf8"
);

function createExtractor() {
  const context = vm.createContext({
    BossPlugin: {
      CONFIG: {
        recruiterActivityMaxDays: 3,
        salaryPrivateUseDigits: "9012345678",
        salaryPrivateUseStart: 0xE030
      },
      SELECTORS: {},
      dom: {},
      logger: { debug() {}, info() {}, warn() {} }
    }
  });
  context.globalThis = context;
  vm.runInContext(extractorSource, context);
  return context.BossPlugin.jobExtractor;
}

test("classifies recruiter activity at the three-day boundary", () => {
  const { parseRecruiterActivity } = createExtractor();
  const allowed = [
    "在线",
    "刚刚活跃",
    "今日活跃",
    "昨日活跃",
    "前天活跃",
    "30分钟内活跃",
    "72小时内活跃",
    "3日内活跃",
    "3 天内活跃"
  ];
  const skipped = [
    "73小时内活跃",
    "4日内活跃",
    "4天内活跃",
    "1周内活跃",
    "2周内活跃",
    "4月内活跃",
    "本周活跃",
    "本月活跃"
  ];

  for (const text of allowed) {
    assert.equal(parseRecruiterActivity(text).withinAllowedRange, true, text);
  }
  for (const text of skipped) {
    assert.equal(parseRecruiterActivity(text).withinAllowedRange, false, text);
  }
  assert.equal(parseRecruiterActivity("活跃时间未知").withinAllowedRange, null);
});

function createScanner(activity) {
  let apiRequestCount = 0;
  let extractJobCount = 0;
  const persisted = [];
  const ns = {
    STATES: {
      WAITING_DETAIL: "WAITING_DETAIL",
      REQUESTING: "REQUESTING",
      COMMUNICATING: "COMMUNICATING",
      RUNNING: "RUNNING",
      PAUSED: "PAUSED"
    },
    CONFIG: {
      recruiterActivityMaxDays: 3,
      detailSettleDelayMinMs: 0,
      detailSettleDelayMaxMs: 0,
      matchThreshold: 70,
      storageKeys: { processedJobs: "processedJobs" }
    },
    MESSAGES: {
      EVALUATE_JOB: "evaluate",
      CANCEL_EVALUATION: "cancel"
    },
    storage: {
      async set(_key, value) {
        persisted.push(value);
      }
    },
    dom: { async delay() {} },
    logger: { info() {}, warn() {}, error() {} },
    jobExtractor: {
      detailSnapshot() { return "before"; },
      async waitForJobDetailUpdate() { return { innerText: "detail" }; },
      getRecruiterActivity() { return activity; },
      extractCurrentJob() {
        extractJobCount += 1;
        return { job_id: "job-1", job_name: "测试岗位", job_description: "岗位描述" };
      }
    },
    communication: { async communicate() {} }
  };
  const context = vm.createContext({
    AbortController,
    DOMException,
    BossPlugin: ns,
    chrome: {
      runtime: {
        lastError: null,
        sendMessage(_message, callback) {
          apiRequestCount += 1;
          callback({ ok: true, data: { match_score: 65 } });
        }
      }
    },
    crypto: { randomUUID: () => "request-1" }
  });
  context.globalThis = context;
  vm.runInContext(scannerSource, context);

  const state = {
    value: { scannedCount: 0, matchedCount: 0 },
    async transition(status, changes = {}) {
      this.value = { ...this.value, ...changes, status };
      return this.value;
    },
    async patch(changes) {
      this.value = { ...this.value, ...changes };
      return this.value;
    }
  };
  const scanner = new ns.JobScanner(state);
  scanner.waitBeforeJobClick = async () => {};

  return {
    scanner,
    state,
    getApiRequestCount: () => apiRequestCount,
    getExtractJobCount: () => extractJobCount,
    persisted
  };
}

function connectedCard() {
  return {
    isConnected: true,
    scrollIntoView() {},
    click() {}
  };
}

test("skips an inactive recruiter without extracting or calling FastAPI", async () => {
  const harness = createScanner({ text: "2周内活跃", withinAllowedRange: false });
  const controller = new AbortController();

  await harness.scanner.processOne(
    connectedCard(),
    { jobId: "job-1", title: "测试岗位" },
    controller.signal
  );

  assert.equal(harness.getApiRequestCount(), 0);
  assert.equal(harness.getExtractJobCount(), 0);
  assert.equal(harness.state.value.scannedCount, 0);
  assert.equal(harness.scanner.processedJobs.has("job-1"), true);
  assert.equal(harness.persisted.length, 1);
});

test("keeps the original FastAPI flow for activity within three days", async () => {
  const harness = createScanner({ text: "3日内活跃", withinAllowedRange: true });
  const controller = new AbortController();

  await harness.scanner.processOne(
    connectedCard(),
    { jobId: "job-1", title: "测试岗位" },
    controller.signal
  );

  assert.equal(harness.getApiRequestCount(), 1);
  assert.equal(harness.getExtractJobCount(), 1);
  assert.equal(harness.state.value.scannedCount, 1);
  assert.equal(harness.state.value.currentScore, 65);
});
