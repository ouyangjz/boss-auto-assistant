(() => {
  const ns = (globalThis.BossPlugin ??= {});

  ns.STATES = Object.freeze({
    IDLE: "IDLE",
    RUNNING: "RUNNING",
    PAUSED: "PAUSED",
    WAITING_DETAIL: "WAITING_DETAIL",
    REQUESTING: "REQUESTING",
    COMMUNICATING: "COMMUNICATING",
    FINISHED: "FINISHED",
    ERROR: "ERROR",
    STOPPED: "STOPPED"
  });

  ns.MESSAGES = Object.freeze({
    CONTROL: "BOSS_PLUGIN_CONTROL",
    EVALUATE_JOB: "BOSS_PLUGIN_EVALUATE_JOB",
    CANCEL_EVALUATION: "BOSS_PLUGIN_CANCEL_EVALUATION",
    PING: "BOSS_PLUGIN_PING"
  });

  ns.CONFIG = Object.freeze({
    apiUrl: "http://127.0.0.1:8000/api/v1/jobs/evaluate",
    bulkApiUrl: "http://127.0.0.1:8000/api/v1/jobs/bulk-evaluate",
    recruiterActivityMaxDays: 3,
    // Coze 工作流通常需要 60～90 秒；需长于 FastAPI 的 Coze 超时，
    // 才能让插件收到后端的成功响应或明确错误。
    requestTimeoutMs: 120000,
    detailTimeoutMs: 8000,
    modalTimeoutMs: 8000,
    modalCloseTimeoutMs: 5000,
    modalDismissDelayMinMs: 1000,
    modalDismissDelayMaxMs: 2000,
    pollingIntervalMs: 150,
    initialJobDelayMinMs: 1800,
    initialJobDelayMaxMs: 3000,
    jobSwitchIntervalMinMs: 1000,
    jobSwitchIntervalMaxMs: 2000,
    detailSettleDelayMinMs: 500,
    detailSettleDelayMaxMs: 1000,
    // BOSS 当前薪资字体把数字 9,0,1...8 顺序映射到 U+E030...U+E039。
    salaryPrivateUseDigits: "9012345678",
    salaryPrivateUseStart: 0xE030,
    scrollRatio: 0.8,
    scrollLoadWaitMs: 2500,
    maxEmptyScrolls: 3,
    debugSelectors: true,
    storageKeys: Object.freeze({
      taskState: "bossPluginTaskState",
      processedJobs: "bossPluginProcessedJobs",
      bulkApplyEnabled: "bossPluginBulkApplyEnabled"
    })
  });
})();
