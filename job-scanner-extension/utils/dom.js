(() => {
  const ns = (globalThis.BossPlugin ??= {});

  function queryFirst(selectors, root = document, debugName = "") {
    for (const selector of selectors) {
      try {
        const element = root.querySelector(selector);
        if (element) {
          if (ns.CONFIG.debugSelectors && debugName) {
            ns.logger.debug(`[Selector] ${debugName} => ${selector}`, element);
          }
          return element;
        }
      } catch (error) {
        ns.logger.warn(`无效 selector: ${selector}`, error);
      }
    }
    return null;
  }

  function queryAll(selectors, root = document) {
    const found = [];
    const seen = new Set();
    for (const selector of selectors) {
      try {
        for (const element of root.querySelectorAll(selector)) {
          if (!seen.has(element)) {
            seen.add(element);
            found.push(element);
          }
        }
      } catch (error) {
        ns.logger.warn(`无效 selector: ${selector}`, error);
      }
    }
    return found;
  }

  function normalizedText(element) {
    return (element?.textContent || "").replace(/\s+/g, " ").trim();
  }

  function findTextWithin(root, selectors, expectedText) {
    if (!root) return null;
    return queryAll(selectors, root).find((element) => normalizedText(element) === expectedText) || null;
  }

  function abortError() {
    return new DOMException("操作已停止", "AbortError");
  }

  function delay(ms, signal) {
    return new Promise((resolve, reject) => {
      if (signal?.aborted) return reject(abortError());
      const timer = setTimeout(cleanupAndResolve, ms);
      const onAbort = () => {
        clearTimeout(timer);
        signal?.removeEventListener("abort", onAbort);
        reject(abortError());
      };
      function cleanupAndResolve() {
        signal?.removeEventListener("abort", onAbort);
        resolve();
      }
      signal?.addEventListener("abort", onAbort, { once: true });
    });
  }

  function waitFor(predicate, { timeoutMs, intervalMs = 150, signal } = {}) {
    return new Promise((resolve, reject) => {
      if (signal?.aborted) return reject(abortError());
      let settled = false;
      let observer;
      let interval;
      let timeout;

      const cleanup = () => {
        observer?.disconnect();
        clearInterval(interval);
        clearTimeout(timeout);
        signal?.removeEventListener("abort", onAbort);
      };
      const finish = (value) => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(value);
      };
      const fail = (error) => {
        if (settled) return;
        settled = true;
        cleanup();
        reject(error);
      };
      const check = () => {
        try {
          const value = predicate();
          if (value) finish(value);
        } catch (error) {
          fail(error);
        }
      };
      const onAbort = () => fail(abortError());

      observer = new MutationObserver(check);
      observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
      interval = setInterval(check, intervalMs);
      timeout = setTimeout(() => finish(null), timeoutMs ?? 8000);
      signal?.addEventListener("abort", onAbort, { once: true });
      check();
    });
  }

  ns.dom = Object.freeze({ queryFirst, queryAll, normalizedText, findTextWithin, delay, waitFor });
})();

