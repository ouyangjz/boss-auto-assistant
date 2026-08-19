"use strict";

(() => {
  if (globalThis.__CHAT_ASSISTANT_CONTENT_SCRIPT_LOADED__ === true) {
    console.log("[ChatAssistant][Content] already loaded; skip duplicate registration");
    return;
  }

  const CONFIG = globalThis.ChatAssistantConfig;
  if (!CONFIG?.selectors || !CONFIG?.messageType) {
    throw new Error("ChatAssistantConfig is unavailable");
  }
  globalThis.__CHAT_ASSISTANT_CONTENT_SCRIPT_LOADED__ = true;
  const SELECTORS = CONFIG.selectors;
  let taskQueue = Promise.resolve();

  function log(scope, message, ...details) {
    console.log(`[ChatAssistant][${scope}] ${message}`, ...details);
  }

  function normalizeText(value) {
    return String(value || "").replace(/[\s\u00a0\u3000]+/g, "").trim();
  }

  function isVisible(element) {
    if (!element?.isConnected || element.getClientRects().length === 0) return false;
    const style = window.getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden";
  }

  function queryAll(selectors, root = document) {
    const nodes = [];
    for (const selector of selectors) {
      try {
        nodes.push(...root.querySelectorAll(selector));
      } catch (error) {
        log("DOM", `invalid selector ${selector}`, error);
      }
    }
    return [...new Set(nodes)];
  }

  function isScrollable(element) {
    if (!element || !isVisible(element)) return false;
    const style = window.getComputedStyle(element);
    return /(auto|scroll|overlay)/i.test(style.overflowY || style.overflow) &&
      element.scrollHeight > element.clientHeight + 10;
  }

  function getContactRows() {
    let rows = queryAll(SELECTORS.contactItem).filter((row) => {
      if (!isVisible(row)) return false;
      const rect = row.getBoundingClientRect();
      return rect.left < window.innerWidth * 0.46 &&
        rect.width >= 150 && rect.width <= 700 &&
        rect.height >= 36 && rect.height <= 180 &&
        normalizeText(row.textContent).length >= 2;
    });

    if (!rows.length) {
      rows = [...document.querySelectorAll("li[role='listitem'], li")].filter((row) => {
        if (!isVisible(row)) return false;
        const rect = row.getBoundingClientRect();
        const text = normalizeText(row.textContent);
        return rect.left < window.innerWidth * 0.46 && rect.width >= 180 &&
          rect.height >= 45 && rect.height <= 150 && text.length >= 2 && text.length <= 300;
      });
    }

    return rows.filter((row, index, allRows) => !allRows.some((other, otherIndex) => {
      if (index === otherIndex || !other.contains(row)) return false;
      const sameText = normalizeText(other.textContent) === normalizeText(row.textContent);
      return sameText;
    }));
  }

  function scoreCandidate(row, task) {
    const text = normalizeText(row.textContent);
    const hrName = normalizeText(task.hr_name);
    const companyName = normalizeText(task.company_name);
    const hrTitle = normalizeText(task.hr_title);
    const hasHrName = Boolean(hrName && text.includes(hrName));
    const hasCompany = Boolean(companyName && text.includes(companyName));
    const hasHrTitle = Boolean(hrTitle && text.includes(hrTitle));

    if (!hasHrName || (!hasCompany && !hasHrTitle)) return null;
    return {
      row,
      score: (hasHrName ? 5 : 0) + (hasCompany ? 3 : 0) + (hasHrTitle ? 2 : 0)
    };
  }

  function findBestCandidate(task) {
    const matches = getContactRows()
      .map((row) => scoreCandidate(row, task))
      .filter(Boolean)
      .sort((left, right) => right.score - left.score);
    if (!matches.length) return { status: "not_found" };

    const topScore = matches[0].score;
    const topMatches = matches.filter((item) => item.score === topScore);
    const distinct = [];
    for (const item of topMatches) {
      const duplicate = distinct.some((other) => {
        const sameText = normalizeText(item.row.textContent) === normalizeText(other.row.textContent);
        return sameText && (other.row.contains(item.row) || item.row.contains(other.row));
      });
      if (!duplicate) distinct.push(item);
    }
    if (distinct.length > 1) return { status: "ambiguous", score: topScore };
    return { status: "matched", row: distinct[0].row, score: topScore };
  }

  function findContactList() {
    const direct = queryAll(SELECTORS.contactList).find((element) => isScrollable(element));
    if (direct) return direct;

    const rows = getContactRows();
    const candidates = new Set();
    for (const row of rows) {
      let parent = row.parentElement;
      while (parent && parent !== document.body) {
        if (isScrollable(parent)) candidates.add(parent);
        parent = parent.parentElement;
      }
    }
    return [...candidates].sort((left, right) => {
      const leftCount = rows.filter((row) => left.contains(row)).length;
      const rightCount = rows.filter((row) => right.contains(row)).length;
      return rightCount - leftCount;
    })[0] || null;
  }

  async function delay(milliseconds) {
    await new Promise((resolve) => setTimeout(resolve, milliseconds));
  }

  async function waitForMutationOrTimeout(milliseconds) {
    await new Promise((resolve) => {
      let finished = false;
      let observer;
      let timer;
      const complete = () => {
        if (finished) return;
        finished = true;
        observer?.disconnect();
        clearTimeout(timer);
        resolve();
      };
      observer = new MutationObserver(complete);
      timer = setTimeout(complete, milliseconds);
      observer.observe(document.body || document.documentElement, {
        childList: true,
        subtree: true,
        characterData: true
      });
    });
  }

  async function scanVirtualList(task, scrollBudget) {
    let result = findBestCandidate(task);
    if (result.status !== "not_found") return result;

    const container = findContactList();
    if (!container) return result;
    const originalTop = container.scrollTop;
    container.scrollTop = 0;
    container.dispatchEvent(new Event("scroll", { bubbles: true }));
    await delay(CONFIG.scrollStepDelayMs);

    const step = Math.max(100, Math.floor(container.clientHeight * 0.75));
    while (scrollBudget.remaining > 0) {
      result = findBestCandidate(task);
      if (result.status !== "not_found") return result;

      const before = Math.round(container.scrollTop);
      const maxTop = Math.max(0, container.scrollHeight - container.clientHeight);
      if (before >= maxTop - 2) break;
      scrollBudget.remaining -= 1;
      container.scrollTop = Math.min(maxTop, before + step);
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
      await delay(CONFIG.scrollStepDelayMs);
    }

    result = findBestCandidate(task);
    if (result.status === "not_found") {
      container.scrollTop = originalTop;
      container.dispatchEvent(new Event("scroll", { bubbles: true }));
    }
    return result;
  }

  async function waitForCandidate(task) {
    const startedAt = Date.now();
    const scrollBudget = { remaining: CONFIG.maxScrollSteps };
    for (const retryDelay of CONFIG.candidateRetryDelaysMs) {
      if (Date.now() - startedAt >= CONFIG.maxCandidateWaitMs) break;
      if (retryDelay) await waitForMutationOrTimeout(retryDelay);
      log("Candidate", "scanning...");
      const result = await scanVirtualList(task, scrollBudget);
      if (result.status !== "not_found") return result;
    }
    return { status: "not_found" };
  }

  function getCandidateClickTargets(row) {
    if (!row) return [];
    const descendants = queryAll(SELECTORS.contactClickTarget, row);
    const ancestors = [];
    let ancestor = row.parentElement;
    for (let depth = 0; ancestor && depth < 3; depth += 1) {
      if (ancestor.matches("li, [role='listitem'], [class*='friend-content']")) {
        ancestors.push(ancestor);
      }
      ancestor = ancestor.parentElement;
    }

    return [...new Set([row, ...descendants, ...ancestors])].filter((element) => {
      if (!isVisible(element)) return false;
      const label = normalizeText(
        `${element.getAttribute?.("aria-label") || ""}${element.getAttribute?.("title") || ""}`
      );
      const className = String(element.className || "");
      return !/更多|删除|关闭|移除/.test(label) &&
        !/more|delete|close|remove|checkbox/i.test(className);
    });
  }

  function findChatHeader(task) {
    const hrName = normalizeText(task.hr_name);
    const companyName = normalizeText(task.company_name);
    const isMatchingHeader = (element) => {
      if (!isVisible(element)) return false;
      const rect = element.getBoundingClientRect();
      const text = normalizeText(element.textContent);
      return rect.left > window.innerWidth * 0.3 && rect.top < window.innerHeight * 0.42 &&
        text.includes(hrName) && text.includes(companyName);
    };
    const direct = queryAll(SELECTORS.chatHeader).filter(isMatchingHeader);
    if (direct.length) {
      return direct.sort((left, right) => {
        const leftRect = left.getBoundingClientRect();
        const rightRect = right.getBoundingClientRect();
        return leftRect.width * leftRect.height - rightRect.width * rightRect.height;
      })[0];
    }

    return [...document.querySelectorAll("header, section, div")]
      .filter((element) => {
        if (!isMatchingHeader(element)) return false;
        const rect = element.getBoundingClientRect();
        return rect.width >= 220 && rect.height <= 220 &&
          normalizeText(element.textContent).length <= 500;
      })
      .sort((left, right) => {
        const leftRect = left.getBoundingClientRect();
        const rightRect = right.getBoundingClientRect();
        return leftRect.width * leftRect.height - rightRect.width * rightRect.height;
      })[0] || null;
  }

  function isActiveChatVerified(task) {
    const header = findChatHeader(task);
    if (!header) return false;
    const text = normalizeText(header.textContent);
    return text.includes(normalizeText(task.hr_name)) &&
      text.includes(normalizeText(task.company_name));
  }

  async function waitForActiveChat(task, timeoutMs = CONFIG.chatVerifyTimeoutMs) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < timeoutMs) {
      if (isActiveChatVerified(task)) return true;
      await waitForMutationOrTimeout(250);
    }
    return isActiveChatVerified(task);
  }

  async function openCandidateAndVerify(row, task) {
    if (!row?.isConnected) return { verified: false, selectionMode: "row_disconnected" };
    if (isActiveChatVerified(task)) {
      log("Chat", "target conversation is already active");
      return { verified: true, selectionMode: "already_active", clickAttempt: 0 };
    }

    const targets = getCandidateClickTargets(row);
    const deadline = Date.now() + CONFIG.chatVerifyTimeoutMs;
    log("Candidate", `trying ${targets.length} safe click target(s)`);
    for (let index = 0; index < targets.length; index += 1) {
      const target = targets[index];
      if (!target?.isConnected || !isVisible(target)) continue;
      const remainingMs = deadline - Date.now();
      if (remainingMs <= 0) break;

      target.scrollIntoView({ block: "center", inline: "nearest" });
      target.focus?.({ preventScroll: true });
      const targetName = `${target.tagName || "node"}.${String(target.className || "")}`
        .replace(/\s+/g, ".")
        .slice(0, 100);
      log("Candidate", `click attempt=${index + 1}/${targets.length} target=${targetName}`);
      target.click();

      const attemptTimeoutMs = Math.min(2000, Math.max(500, remainingMs));
      if (await waitForActiveChat(task, attemptTimeoutMs)) {
        log("Chat", `verified after click attempt=${index + 1}`);
        return {
          verified: true,
          selectionMode: "clicked",
          clickAttempt: index + 1,
          clickTarget: targetName
        };
      }
    }
    return {
      verified: isActiveChatVerified(task),
      selectionMode: "click_unverified",
      clickAttempt: targets.length
    };
  }

  function findMessageInput() {
    return queryAll(SELECTORS.messageInput)
      .filter((element) => {
        if (!isVisible(element) || element.disabled || element.readOnly) return false;
        const rect = element.getBoundingClientRect();
        return rect.left > window.innerWidth * 0.3 &&
          rect.top > window.innerHeight * 0.5 && rect.width >= 180;
      })
      .sort((left, right) =>
        right.getBoundingClientRect().width - left.getBoundingClientRect().width
      )[0] || null;
  }

  function isActionable(element) {
    if (!isVisible(element) || element.disabled || element.getAttribute?.("aria-disabled") === "true") {
      return false;
    }
    const style = window.getComputedStyle(element);
    return style.pointerEvents !== "none";
  }

  function findSendButton(input) {
    if (!input) return null;
    const inputRect = input.getBoundingClientRect();
    return queryAll(SELECTORS.sendButton)
      .filter((element) => {
        if (!isActionable(element)) return false;
        const rect = element.getBoundingClientRect();
        const text = normalizeText(
          element.innerText || element.textContent || element.getAttribute?.("aria-label")
        );
        return text === "发送" &&
          rect.left > window.innerWidth * 0.55 &&
          rect.top > window.innerHeight * 0.55 &&
          Math.abs(rect.bottom - inputRect.bottom) < 260;
      })
      .sort((left, right) => {
        const leftRect = left.getBoundingClientRect();
        const rightRect = right.getBoundingClientRect();
        const leftDistance = Math.abs(leftRect.left - inputRect.right) +
          Math.abs(leftRect.bottom - inputRect.bottom);
        const rightDistance = Math.abs(rightRect.left - inputRect.right) +
          Math.abs(rightRect.bottom - inputRect.bottom);
        return leftDistance - rightDistance;
      })[0] || null;
  }

  function getInputValue(input) {
    if (!input) return "";
    return input.isContentEditable
      ? String(input.innerText || input.textContent || "")
      : String(input.value || "");
  }

  function setNativeInputValue(input, value) {
    const prototype = input instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
    if (descriptor?.set) descriptor.set.call(input, value);
    else input.value = value;
  }

  function replaceContentEditableText(input, value) {
    input.focus();
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(input);
    selection.removeAllRanges();
    selection.addRange(range);
    try {
      document.execCommand("delete", false, null);
      const inserted = value ? document.execCommand("insertText", false, value) : true;
      if (!inserted) input.textContent = value;
    } catch (error) {
      input.textContent = value;
    } finally {
      selection.removeAllRanges();
    }
  }

  function fillInput(input, value) {
    input.focus();
    if (input.isContentEditable) replaceContentEditableText(input, value);
    else setNativeInputValue(input, value);
    try {
      input.dispatchEvent(new InputEvent("input", {
        bubbles: true,
        inputType: "insertText",
        data: value
      }));
    } catch (error) {
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function verifyFilledValue(input, value) {
    const expected = normalizeText(value);
    const startedAt = Date.now();
    let stableChecks = 0;
    while (Date.now() - startedAt < CONFIG.inputVerifyTimeoutMs) {
      if (!input?.isConnected) return false;
      if (normalizeText(getInputValue(input)) === expected) {
        stableChecks += 1;
        if (stableChecks >= 3) return true;
      } else {
        stableChecks = 0;
      }
      await delay(120);
    }
    return false;
  }

  async function verifyMessageSent(input) {
    const startedAt = Date.now();
    while (Date.now() - startedAt < CONFIG.sendVerifyTimeoutMs) {
      if (!input?.isConnected) return true;
      if (!normalizeText(getInputValue(input))) return true;
      await delay(120);
    }
    return !input?.isConnected || !normalizeText(getInputValue(input));
  }

  async function sendFilledGreeting(input, task) {
    const expected = normalizeText(task.greeting_message);
    const waitMs = Math.round(
      CONFIG.sendDelayMinMs +
      Math.random() * Math.max(0, CONFIG.sendDelayMaxMs - CONFIG.sendDelayMinMs)
    );
    log("Send", `auto-send enabled; waiting ${waitMs}ms`);
    await delay(waitMs);

    if (!isActiveChatVerified(task)) {
      log("Send", "cancelled because active conversation changed");
      return "send_cancelled_chat_changed";
    }
    if (!input?.isConnected || normalizeText(getInputValue(input)) !== expected) {
      log("Send", "cancelled because greeting draft changed");
      return "send_cancelled_draft_changed";
    }

    const sendButton = findSendButton(input);
    if (!sendButton) {
      log("Send", "send button not found");
      return "send_button_not_found";
    }

    log("Send", "clicking send button");
    sendButton.click();
    const sent = await verifyMessageSent(input);
    log("Send", sent ? "message sent" : "send result could not be verified");
    return sent ? "sent" : "send_unverified";
  }

  async function processIntroduction(task) {
    log(
      "Candidate",
      `hr_name=${task.hr_name} company_name=${task.company_name} hr_title=${task.hr_title}`
    );
    const match = await waitForCandidate(task);
    if (match.status === "ambiguous") {
      log("Candidate", `ambiguous score=${match.score}`);
      return { status: "ambiguous_candidate" };
    }
    if (match.status !== "matched") {
      log("Candidate", "not found");
      return { status: "candidate_not_found" };
    }

    log("Candidate", `matched score=${match.score}`);
    log("Candidate", "clicking");
    const selection = await openCandidateAndVerify(match.row, task);
    if (!selection.verified) {
      log("Chat", "verification failed");
      return {
        status: "chat_verification_failed",
        selection_mode: selection.selectionMode
      };
    }

    const input = findMessageInput();
    if (!input) {
      log("Input", "input not found");
      return { status: "input_not_found" };
    }

    log("Input", "filling greeting");
    fillInput(input, String(task.greeting_message || ""));
    const verified = await verifyFilledValue(input, task.greeting_message);
    if (!verified || !isActiveChatVerified(task)) {
      log("Input", "fill verification failed");
      return { status: "input_not_found" };
    }

    if (task.auto_send === true) {
      const sendStatus = await sendFilledGreeting(input, task);
      return {
        status: sendStatus,
        selection_mode: selection.selectionMode,
        click_attempt: selection.clickAttempt || 0
      };
    }

    // 自动发送关闭时到此结束，不点击发送按钮，也不模拟 Enter。
    log(
      "Task",
      `completed task=${task.task_id} selection_mode=${selection.selectionMode}`
    );
    return {
      status: "filled",
      selection_mode: selection.selectionMode,
      click_attempt: selection.clickAttempt || 0
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== CONFIG.messageType) return false;
    taskQueue = taskQueue
      .catch(() => undefined)
      .then(() => processIntroduction(message.payload));
    taskQueue
      .then(sendResponse)
      .catch((error) => {
        log("Task", "unexpected processing failure", error);
        sendResponse({ status: "input_not_found" });
      });
    return true;
  });

  globalThis.__CHAT_ASSISTANT_DEBUG__ = Object.freeze({
    normalizeText,
    getContactRows,
    findBestCandidate,
    findContactList,
    getCandidateClickTargets,
    openCandidateAndVerify,
    findChatHeader,
    findMessageInput,
    findSendButton,
    isActiveChatVerified
  });

  log("Content", "ready; auto-send is controlled by the extension popup");
})();
