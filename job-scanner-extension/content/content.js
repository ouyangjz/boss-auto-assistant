(() => {
  const ns = globalThis.BossPlugin;
  const state = new ns.StateManager();
  const scanner = new ns.JobScanner(state);
  const ready = scanner.initialize();

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === ns.MESSAGES.PING) {
      sendResponse({ ok: true });
      return false;
    }
    if (message?.type !== ns.MESSAGES.CONTROL) return false;

    (async () => {
      await ready;
      if (message.command === "START") await scanner.startOrResume();
      else if (message.command === "PAUSE") await scanner.pause();
      else if (message.command === "STOP") await scanner.stop();
      else if (message.command === "CLEAR_CURRENT") await scanner.reset();
      else throw new Error(`未知命令: ${message.command}`);
      sendResponse({ ok: true, state: state.value });
    })().catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  });

  // 这些函数只做调试，不参与业务循环；可直接在页面 DevTools Console 调用。
  window.__BOSS_PLUGIN_DEBUG__ = Object.freeze({
    findJobList: ns.jobExtractor.findJobList,
    findScrollContainer: ns.jobExtractor.findScrollContainer,
    getVisibleJobs: ns.jobExtractor.getVisibleJobs,
    extractCurrentJob: ns.jobExtractor.extractCurrentJob,
    findJobDescriptionElement: ns.jobExtractor.findJobDescriptionElement,
    findCommunicateButton: ns.communication.findCommunicateButton,
    findCommunicationModal: ns.communication.findCommunicationModal,
    findCommunicationCloseButton: ns.communication.findCloseButton,
    printSelectors() {
      const result = {};
      for (const [name, selectors] of Object.entries(ns.SELECTORS)) {
        result[name] = selectors.map((selector) => ({ selector, count: document.querySelectorAll(selector).length }));
      }
      console.table(Object.entries(result).flatMap(([name, rows]) => rows.map((row) => ({ name, ...row }))));
      return result;
    }
  });

  ns.logger.info("Content Script 已加载；可使用 window.__BOSS_PLUGIN_DEBUG__ 调试 selector");
})();
