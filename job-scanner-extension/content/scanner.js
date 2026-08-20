(() => {
  const ns = (globalThis.BossPlugin ??= {});

  function sendMessage(message, signal) {
    return new Promise((resolve, reject) => {
      let settled = false;
      const requestId = crypto.randomUUID();
      const fullMessage = { ...message, requestId };
      const cleanup = () => signal?.removeEventListener("abort", onAbort);
      const onAbort = () => {
        if (settled) return;
        settled = true;
        cleanup();
        chrome.runtime.sendMessage({ type: ns.MESSAGES.CANCEL_EVALUATION, requestId }, () => {
          void chrome.runtime.lastError;
        });
        reject(new DOMException("操作已停止", "AbortError"));
      };
      if (signal?.aborted) return onAbort();
      signal?.addEventListener("abort", onAbort, { once: true });
      chrome.runtime.sendMessage(fullMessage, (response) => {
        if (settled) return;
        settled = true;
        cleanup();
        const error = chrome.runtime.lastError;
        if (error) reject(new Error(error.message));
        else resolve(response);
      });
    });
  }

  class JobScanner {
    constructor(stateManager) {
      this.state = stateManager;
      this.processedJobs = new Set();
      this.pauseRequested = false;
      this.stopRequested = false;
      this.loopPromise = null;
      this.controller = null;
      this.lastJobClickAt = 0;
    }

    async initialize() {
      await this.state.load();
      const saved = await ns.storage.get(ns.CONFIG.storageKeys.processedJobs, []);
      this.processedJobs = new Set(Array.isArray(saved) ? saved : []);
    }

    async startOrResume() {
      this.pauseRequested = false;
      this.stopRequested = false;
      if (this.loopPromise) {
        await this.state.transition(ns.STATES.RUNNING, { lastError: "" });
        return;
      }
      this.controller = new AbortController();
      await this.state.transition(ns.STATES.RUNNING, { lastError: "" });
      this.loopPromise = this.run(this.controller.signal).finally(() => {
        this.loopPromise = null;
        this.controller = null;
      });
    }

    async pause() {
      this.pauseRequested = true;
      if (!this.loopPromise) await this.state.transition(ns.STATES.PAUSED);
    }

    async stop() {
      this.stopRequested = true;
      this.pauseRequested = false;
      this.controller?.abort();
      await this.state.transition(ns.STATES.STOPPED);
    }

    async reset() {
      // 先停止并等待旧循环完全退出，避免旧任务在清空后再次写回 processedJobs。
      this.stopRequested = true;
      this.pauseRequested = false;
      this.controller?.abort();
      const activeLoop = this.loopPromise;
      if (activeLoop) {
        try {
          await activeLoop;
        } catch (_error) {
          // run() 已负责记录非中止错误；重置流程继续完成清理。
        }
      }

      this.processedJobs.clear();
      await this.persistProcessed();
      this.lastJobClickAt = 0;
      this.stopRequested = false;

      const list = ns.jobExtractor.findJobList();
      const scroller = list ? ns.jobExtractor.findScrollContainer(list) : null;
      if (scroller) {
        scroller.scrollTop = 0;
        if (scroller === document.scrollingElement || scroller === document.documentElement) {
          window.scrollTo({ top: 0, behavior: "auto" });
          window.dispatchEvent(new Event("scroll"));
        } else {
          scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
        }
        // 虚拟列表回到顶部后需要等待首批卡片完成替换，再允许下一次启动。
        await ns.dom.delay(ns.CONFIG.scrollLoadWaitMs);
      }

      await this.state.transition(ns.STATES.IDLE, {
        currentJob: "",
        scannedCount: 0,
        matchedCount: 0,
        currentScore: null,
        lastError: ""
      });
      ns.logger.info("扫描记录已清空，下次开始将从列表顶部重新处理");
    }

    async waitWhilePaused(signal) {
      if (!this.pauseRequested) return;
      await this.state.transition(ns.STATES.PAUSED);
      while (this.pauseRequested && !this.stopRequested) {
        await ns.dom.delay(200, signal);
      }
      if (!this.stopRequested) await this.state.transition(ns.STATES.RUNNING, { lastError: "" });
    }

    async persistProcessed() {
      await ns.storage.set(ns.CONFIG.storageKeys.processedJobs, [...this.processedJobs]);
    }

    randomDelay(minimum, maximum) {
      return Math.round(minimum + Math.random() * Math.max(0, maximum - minimum));
    }

    async waitCooldown(waitMs, signal) {
      let remaining = waitMs;
      while (remaining > 0) {
        await this.waitWhilePaused(signal);
        const slice = Math.min(remaining, 250);
        await ns.dom.delay(slice, signal);
        remaining -= slice;
      }
    }

    async waitBeforeJobClick(signal) {
      const targetInterval = this.randomDelay(
        ns.CONFIG.jobSwitchIntervalMinMs,
        ns.CONFIG.jobSwitchIntervalMaxMs
      );
      const waitMs = this.lastJobClickAt
        ? Math.max(0, targetInterval - (Date.now() - this.lastJobClickAt))
        : this.randomDelay(ns.CONFIG.initialJobDelayMinMs, ns.CONFIG.initialJobDelayMaxMs);
      if (waitMs > 0) {
        ns.logger.info(`岗位切换限速等待 ${(waitMs / 1000).toFixed(1)} 秒`);
        await this.waitCooldown(waitMs, signal);
      }
      // 等待期间用户可能点击了暂停；必须在真正操作 DOM 前再次检查。
      await this.waitWhilePaused(signal);
      if (this.stopRequested) throw new DOMException("操作已停止", "AbortError");
    }

    async run(signal) {
      let emptyScrolls = 0;
      try {
        if (!ns.jobExtractor.findJobList()) throw new Error("JOB_LIST_NOT_FOUND");

        while (!this.stopRequested) {
          await this.waitWhilePaused(signal);
          if (this.stopRequested) break;

          // SPA 更新可能直接替换列表节点，因此每轮重新定位而不长期持有旧引用。
          const list = ns.jobExtractor.findJobList();
          if (!list) throw new Error("JOB_LIST_NOT_FOUND");
          const scroller = ns.jobExtractor.findScrollContainer(list);
          if (!scroller) throw new Error("JOB_SCROLL_CONTAINER_NOT_FOUND");
          const cards = ns.jobExtractor.getVisibleJobs(list);
          ns.logger.info(`找到 ${cards.length} 个可见岗位`);
          const candidate = cards
            .map((card) => ({ card, identity: ns.jobExtractor.getCardIdentity(card) }))
            .find(({ identity }) => identity.jobId && !this.processedJobs.has(identity.jobId));

          if (candidate) {
            emptyScrolls = 0;
            await this.processOne(candidate.card, candidate.identity, signal);
            continue;
          }

          const idsBefore = new Set(cards.map((card) => ns.jobExtractor.getCardIdentity(card).jobId));
          const previousTop = scroller.scrollTop;
          const viewportHeight = scroller === document.scrollingElement
            ? window.innerHeight
            : scroller.clientHeight;
          scroller.scrollTop = Math.min(
            scroller.scrollTop + Math.max(viewportHeight * ns.CONFIG.scrollRatio, 200),
            scroller.scrollHeight
          );
          if (scroller === document.scrollingElement || scroller === document.documentElement) {
            window.dispatchEvent(new Event("scroll"));
            ns.logger.info("滚动全局页面以加载更多岗位");
          } else {
            scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
            ns.logger.info("滚动岗位列表容器");
          }
          await ns.dom.delay(ns.CONFIG.scrollLoadWaitMs, signal);

          const after = ns.jobExtractor.getVisibleJobs(list);
          const hasNewId = after.some((card) => !idsBefore.has(ns.jobExtractor.getCardIdentity(card).jobId));
          const moved = scroller.scrollTop !== previousTop;
          emptyScrolls = hasNewId || moved ? (hasNewId ? 0 : emptyScrolls + 1) : emptyScrolls + 1;
          if (emptyScrolls >= ns.CONFIG.maxEmptyScrolls) {
            await this.state.transition(ns.STATES.FINISHED);
            ns.logger.info("扫描完成");
            return;
          }
        }
      } catch (error) {
        if (error?.name === "AbortError" || this.stopRequested) return;
        ns.logger.error(error.message || "UNKNOWN_ERROR", error);
        await this.state.transition(ns.STATES.ERROR, { lastError: error.message || "未知错误" });
      }
    }

    async processOne(card, identity, signal) {
      const before = ns.jobExtractor.detailSnapshot();
      let shouldMarkProcessed = true;
      try {
        ns.logger.info(`当前岗位：${identity.title || identity.jobId}`);
        await this.waitBeforeJobClick(signal);
        if (!card.isConnected) {
          shouldMarkProcessed = false;
          throw new Error("JOB_CARD_STALE");
        }
        card.scrollIntoView({ block: "nearest" });
        card.click();
        this.lastJobClickAt = Date.now();
        await this.state.transition(ns.STATES.WAITING_DETAIL, { currentJob: identity.title || identity.jobId });

        const detail = await ns.jobExtractor.waitForJobDetailUpdate(before, identity.title, signal);
        if (!detail) throw new Error("JOB_DETAIL_TIMEOUT");
        // 详情标题出现后，给同一详情区域内的描述、HR 等异步子模块短暂稳定时间。
        await ns.dom.delay(this.randomDelay(
          ns.CONFIG.detailSettleDelayMinMs,
          ns.CONFIG.detailSettleDelayMaxMs
        ), signal);
        const recruiterActivity = ns.jobExtractor.getRecruiterActivity(detail);
        if (recruiterActivity.withinAllowedRange === false) {
          ns.logger.info(
            `BOSS 活跃状态为“${recruiterActivity.text}”，超出 ${ns.CONFIG.recruiterActivityMaxDays} 天范围，跳过且不请求 FastAPI`
          );
          return;
        }
        if (recruiterActivity.withinAllowedRange === null) {
          ns.logger.warn("未识别到 BOSS 活跃状态，按原流程继续");
        }
        const job = ns.jobExtractor.extractCurrentJob(identity);
        if (!job?.job_description) throw new Error("JOB_DESCRIPTION_NOT_FOUND");
        ns.logger.info("岗位详情加载完成", job);

        await this.state.transition(ns.STATES.REQUESTING, {
          currentJob: job.job_name,
          scannedCount: this.state.value.scannedCount + 1,
          currentScore: null,
          lastError: ""
        });
        const response = await sendMessage({ type: ns.MESSAGES.EVALUATE_JOB, payload: job }, signal);
        if (!response?.ok) {
          shouldMarkProcessed = false;
          this.pauseRequested = true;
          const friendly = response?.code === "API_UNAVAILABLE"
            ? "本地服务连接失败"
            : response?.error || "FastAPI 请求失败";
          await this.state.transition(ns.STATES.PAUSED, { lastError: friendly });
          ns.logger.error(friendly, response);
          return;
        }

        const score = Number(response.data?.match_score);
        if (!Number.isFinite(score) || score < 0 || score > 100) {
          throw new Error("INVALID_MATCH_SCORE");
        }
        const matched = score >= ns.CONFIG.matchThreshold;
        await this.state.patch({
          currentScore: score,
          matchedCount: this.state.value.matchedCount + (matched ? 1 : 0)
        });
        ns.logger.info(`FastAPI match_score = ${score}`);

        if (matched) {
          await this.state.transition(ns.STATES.COMMUNICATING);
          ns.logger.info("准备点击立即沟通");
          await ns.communication.communicate(signal);
        } else {
          ns.logger.info("匹配度不足，跳过");
        }
      } catch (error) {
        if (error?.name === "AbortError") throw error;
        ns.logger.error(error.message, error);
        const blockingModalError = [
          "COMMUNICATION_MODAL_TIMEOUT",
          "STAY_HERE_BUTTON_NOT_FOUND",
          "COMMUNICATION_MODAL_DISMISS_BUTTON_NOT_FOUND",
          "COMMUNICATION_MODAL_CLOSE_TIMEOUT"
        ].includes(error.message);
        if (blockingModalError) {
          // 弹窗仍覆盖页面时禁止继续点击下一岗位，避免误操作遮罩层下的页面。
          this.pauseRequested = true;
          await this.state.transition(ns.STATES.PAUSED, { lastError: error.message });
        } else {
          await this.state.patch({ lastError: error.message });
        }
      } finally {
        if (shouldMarkProcessed && !this.stopRequested && !signal.aborted) {
          this.processedJobs.add(identity.jobId);
          await this.persistProcessed();
        }
        if (!this.pauseRequested && !this.stopRequested) {
          await this.state.transition(ns.STATES.RUNNING);
        }
      }
    }
  }

  ns.JobScanner = JobScanner;
})();
