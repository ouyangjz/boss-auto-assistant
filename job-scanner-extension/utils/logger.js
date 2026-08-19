(() => {
  const ns = (globalThis.BossPlugin ??= {});
  const levels = ["DEBUG", "INFO", "WARN", "ERROR"];

  function write(level, message, detail) {
    const normalized = levels.includes(level) ? level : "INFO";
    const method = normalized === "ERROR" ? "error" : normalized === "WARN" ? "warn" : "log";
    const args = [`[BOSS Plugin] [${normalized}] ${message}`];
    if (detail !== undefined) args.push(detail);
    console[method](...args);
  }

  ns.logger = Object.freeze({
    debug: (message, detail) => write("DEBUG", message, detail),
    info: (message, detail) => write("INFO", message, detail),
    warn: (message, detail) => write("WARN", message, detail),
    error: (message, detail) => write("ERROR", message, detail)
  });
})();

