(() => {
  const ns = (globalThis.BossPlugin ??= {});

  const initialState = Object.freeze({
    status: ns.STATES.IDLE,
    currentJob: "",
    scannedCount: 0,
    matchedCount: 0,
    currentScore: null,
    lastError: "",
    updatedAt: null
  });

  class StateManager {
    constructor() {
      this.value = { ...initialState };
    }

    async load() {
      this.value = await ns.storage.get(ns.CONFIG.storageKeys.taskState, { ...initialState });
      const interruptedStates = [
        ns.STATES.RUNNING,
        ns.STATES.WAITING_DETAIL,
        ns.STATES.REQUESTING,
        ns.STATES.COMMUNICATING
      ];
      if (interruptedStates.includes(this.value.status)) {
        // 页面刷新会销毁旧 Content Script；不能让 Popup 误以为旧循环仍在运行。
        this.value = {
          ...this.value,
          status: ns.STATES.PAUSED,
          lastError: "页面已重新加载，请点击继续",
          updatedAt: new Date().toISOString()
        };
        await ns.storage.set(ns.CONFIG.storageKeys.taskState, this.value);
      }
      return this.value;
    }

    async patch(changes) {
      this.value = { ...this.value, ...changes, updatedAt: new Date().toISOString() };
      await ns.storage.set(ns.CONFIG.storageKeys.taskState, this.value);
      return this.value;
    }

    async transition(status, changes = {}) {
      return this.patch({ ...changes, status });
    }
  }

  ns.StateManager = StateManager;
  ns.initialTaskState = initialState;
})();
