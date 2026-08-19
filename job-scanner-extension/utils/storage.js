(() => {
  const ns = (globalThis.BossPlugin ??= {});
  ns.storage = Object.freeze({
    async get(key, fallback) {
      const result = await chrome.storage.local.get(key);
      return result[key] ?? fallback;
    },
    async set(key, value) {
      await chrome.storage.local.set({ [key]: value });
    }
  });
})();

