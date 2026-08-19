(() => {
  const ns = (globalThis.BossPlugin ??= {});
  const { SELECTORS, dom } = ns;

  function visibleText(element) {
    return (element?.innerText || element?.textContent || "").replace(/\s+/g, " ").trim();
  }

  function compactText(element) {
    return visibleText(element).replace(/\s+/g, "");
  }

  function isActionable(element) {
    if (!element?.isConnected || element.disabled || element.getAttribute?.("aria-disabled") === "true") return false;
    const style = getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" &&
      style.pointerEvents !== "none" && element.getClientRects().length > 0;
  }

  function isVisible(element) {
    if (!element?.isConnected || element.getClientRects().length === 0) return false;
    const style = getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden";
  }

  function findCommunicateButton() {
    const detailRoot = ns.jobExtractor.findDetailRoot();
    if (!detailRoot) return null;
    return dom.queryFirst(SELECTORS.communicateButton, detailRoot, "communicateButton") ||
      dom.findTextWithin(detailRoot, ["button", "a[role='button']", "a"], "立即沟通");
  }

  function findSemanticModal() {
    const root = document.body || document.documentElement;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let textNode = walker.nextNode();
    while (textNode) {
      const nodeText = (textNode.nodeValue || "").replace(/\s+/g, "");
      if (nodeText.includes("已向BOSS发送消息") || nodeText.includes("已向") || nodeText.includes("发送消息")) {
        let ancestor = textNode.parentElement;
        while (ancestor && ancestor !== document.body && ancestor !== document.documentElement) {
          const text = compactText(ancestor);
          if (text.includes("已向BOSS发送消息") && text.includes("留在此页") &&
              text.includes("继续沟通") && isVisible(ancestor)) {
            ns.logger.debug("通过弹窗文本公共祖先定位沟通成功弹窗", ancestor);
            return ancestor;
          }
          ancestor = ancestor.parentElement;
        }
      }
      textNode = walker.nextNode();
    }
    return null;
  }

  function findCommunicationModal() {
    const semantic = findSemanticModal();
    if (semantic) return semantic;

    const candidates = dom.queryAll(SELECTORS.successModal, document).filter((modal) =>
      compactText(modal).includes("已向BOSS发送消息")
    );
    if (!candidates.length) return null;

    // 优先选择同时包含两个操作按钮、文本范围最小的容器，避免选到页面根节点或遮罩层。
    candidates.sort((left, right) => {
      const leftText = compactText(left);
      const rightText = compactText(right);
      const leftComplete = leftText.includes("留在此页") && leftText.includes("继续沟通") ? 1 : 0;
      const rightComplete = rightText.includes("留在此页") && rightText.includes("继续沟通") ? 1 : 0;
      return rightComplete - leftComplete || leftText.length - rightText.length;
    });
    return candidates[0];
  }

  async function waitForCommunicationModal(signal) {
    return dom.waitFor(findCommunicationModal, {
      timeoutMs: ns.CONFIG.modalTimeoutMs,
      intervalMs: ns.CONFIG.pollingIntervalMs,
      signal
    });
  }

  function findStayHereButton(modal = findCommunicationModal()) {
    if (!modal) return null;

    // 首先在弹窗内按可见文本匹配真实可点击元素，避免隐藏反复制字符干扰 textContent。
    const clickables = dom.queryAll([
      "button", "a", "[role='button']", "input[type='button']",
      "[class*='btn']", "[class*='button']"
    ], modal);
    const exact = clickables.find((element) => compactText(element) === "留在此页" && isActionable(element));
    if (exact) return exact;

    // 文本可能位于 span 等子节点中，向上寻找最近的按钮祖先。
    const textNode = dom.queryAll(["span", "div", "p", "em", "i"], modal)
      .filter((element) => compactText(element) === "留在此页")
      .sort((left, right) => right.querySelectorAll("*").length - left.querySelectorAll("*").length)
      .pop();
    if (textNode) {
      const clickable = textNode.closest("button, a, [role='button'], [class*='btn'], [class*='button']");
      if (clickable && modal.contains(clickable) && isActionable(clickable)) return clickable;
    }

    // selector 仅作为最后 fallback，并再次验证其可见文本，禁止按样式盲点第一个按钮。
    return dom.queryAll(SELECTORS.stayHereButton, modal)
      .find((element) => compactText(element) === "留在此页" && isActionable(element)) || null;
  }

  async function waitForStayHereButton(modal, signal) {
    return dom.waitFor(() => findStayHereButton(modal), {
      timeoutMs: Math.min(ns.CONFIG.modalTimeoutMs, 5000),
      intervalMs: ns.CONFIG.pollingIntervalMs,
      signal
    });
  }

  function findCloseButton(modal = findCommunicationModal()) {
    if (!modal) return null;
    const semanticClickables = dom.queryAll([
      "button", "a", "[role='button']", "[aria-label]", "[title]",
      "span", "i", "em"
    ], modal);

    for (const element of semanticClickables) {
      const label = `${element.getAttribute?.("aria-label") || ""} ${element.getAttribute?.("title") || ""}`.trim();
      const text = compactText(element);
      if (label.includes("关闭") || /^(?:×|✕|✖|X)$/i.test(text)) {
        const clickable = element.closest("button, a, [role='button']") || element;
        if (modal.contains(clickable) && isActionable(clickable)) return clickable;
      }
    }

    return dom.queryAll(SELECTORS.closeModalButton, modal).map((element) =>
      element.closest("button, a, [role='button']") || element
    ).find(isActionable) || null;
  }

  async function waitForCloseButton(modal, signal) {
    return dom.waitFor(() => findCloseButton(modal), {
      timeoutMs: 2500,
      intervalMs: ns.CONFIG.pollingIntervalMs,
      signal
    });
  }

  function isModalClosed(modal) {
    if (!modal?.isConnected) return true;
    const style = getComputedStyle(modal);
    return style.display === "none" || style.visibility === "hidden" ||
      modal.getAttribute("aria-hidden") === "true";
  }

  async function waitForModalClosed(modal, signal) {
    return dom.waitFor(() => isModalClosed(modal), {
      timeoutMs: ns.CONFIG.modalCloseTimeoutMs,
      intervalMs: ns.CONFIG.pollingIntervalMs,
      signal
    });
  }

  async function communicate(signal) {
    const button = findCommunicateButton();
    if (!button) throw new Error("COMMUNICATE_BUTTON_NOT_FOUND");
    button.click();

    const modal = await waitForCommunicationModal(signal);
    if (!modal) throw new Error("COMMUNICATION_MODAL_TIMEOUT");
    ns.logger.info("检测到沟通成功弹窗");

    const dismissDelay = Math.round(
      ns.CONFIG.modalDismissDelayMinMs +
      Math.random() * Math.max(0, ns.CONFIG.modalDismissDelayMaxMs - ns.CONFIG.modalDismissDelayMinMs)
    );
    ns.logger.info(`关闭沟通弹窗前等待 ${(dismissDelay / 1000).toFixed(1)} 秒`);
    await dom.delay(dismissDelay, signal);

    let dismissButton = await waitForStayHereButton(modal, signal);
    let dismissMethod = "留在此页";
    if (!dismissButton) {
      dismissButton = await waitForCloseButton(modal, signal);
      dismissMethod = "右上角关闭按钮";
    }
    if (!dismissButton) throw new Error("COMMUNICATION_MODAL_DISMISS_BUTTON_NOT_FOUND");
    dismissButton.scrollIntoView({ block: "nearest" });
    dismissButton.focus({ preventScroll: true });
    dismissButton.click();
    ns.logger.info(`已点击${dismissMethod}`);

    let closed = await waitForModalClosed(modal, signal);
    if (!closed) {
      // “留在此页”事件未生效时，改用同一弹窗内部的右上角关闭按钮兜底。
      const currentModal = findCommunicationModal();
      const closeButton = currentModal ? await waitForCloseButton(currentModal, signal) : null;
      if (closeButton) {
        ns.logger.warn(`${dismissMethod}点击后弹窗未关闭，尝试右上角关闭按钮`);
        closeButton.click();
        closed = await waitForModalClosed(currentModal, signal);
      }
    }
    if (!closed) throw new Error("COMMUNICATION_MODAL_CLOSE_TIMEOUT");
    ns.logger.info("已点击留在此页");
  }

  ns.communication = Object.freeze({
    findCommunicateButton,
    findCommunicationModal,
    waitForCommunicationModal,
    findStayHereButton,
    waitForStayHereButton,
    findCloseButton,
    communicate
  });
})();
