"use strict";

globalThis.ChatAssistantConfig = Object.freeze({
  websocketUrl: "ws://127.0.0.1:8000/ws/chat-assistant-extension",
  messageType: "CHAT_ASSISTANT_INTRODUCTION_READY",
  reconnectDelaysMs: Object.freeze([1000, 2000, 5000, 10000]),
  heartbeatIntervalMs: 20000,
  candidateRetryDelaysMs: Object.freeze([0, 1000, 2000, 3000, 4000, 5000]),
  maxCandidateWaitMs: 30000,
  maxScrollSteps: 15,
  scrollStepDelayMs: 180,
  chatVerifyTimeoutMs: 8000,
  inputVerifyTimeoutMs: 2500,
  sendVerifyTimeoutMs: 3000,
  sendDelayMinMs: 500,
  sendDelayMaxMs: 1000,
  processedTaskStorageKey: "chatAssistantFilledTaskIds",
  connectionEnabledStorageKey: "chatAssistantConnectionEnabled",
  autoSendStorageKey: "chatAssistantAutoSendEnabled",
  maxStoredTaskIds: 200,
  selectors: Object.freeze({
    contactList: Object.freeze([
      ".user-list-content",
      ".chat-list",
      ".friend-list",
      ".message-list",
      "ul[role='group']",
      "[class*='user-list-content']",
      "[class*='chat-list']",
      "[class*='friend-list']"
    ]),
    contactItem: Object.freeze([
      ".user-list-content .friend-content",
      ".user-list-content .friend-content-warp",
      ".user-list-content li[role='listitem']",
      "ul[role='group'] li[role='listitem'][class]",
      ".friend-list .friend-content",
      ".message-list .friend-content",
      "[class*='chat-list'] li",
      "[class*='conversation'] [class*='item']",
      "[class*='friend-content']",
      "[class*='user-list'] li",
      "[class*='message-list'] li",
      "[class*='contact'] li"
    ]),
    contactClickTarget: Object.freeze([
      ".friend-content-warp",
      ".friend-content",
      "[class*='friend-content']",
      "a[href*='/web/geek/chat']",
      "[role='button']",
      ".figure",
      "[class*='figure']"
    ]),
    chatRoot: Object.freeze([
      ".chat-container",
      ".chat-content",
      ".conversation-content",
      "[class*='chat-container']",
      "[class*='conversation-content']",
      "[class*='chat-content']"
    ]),
    chatHeader: Object.freeze([
      ".chat-header",
      ".chat-title",
      ".chat-basic-info",
      ".name-box",
      "[class*='chat-header']",
      "[class*='chat-title']",
      "[class*='basic-info']"
    ]),
    messageInput: Object.freeze([
      "[contenteditable='true']",
      "textarea",
      "input[type='text']"
    ]),
    sendButton: Object.freeze([
      "button[type='submit']",
      ".send-btn",
      ".send-button",
      "[class*='send-btn']",
      "[class*='send-button']",
      "button",
      "[role='button']"
    ])
  })
});
