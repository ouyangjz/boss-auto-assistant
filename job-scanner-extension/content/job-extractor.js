(() => {
  const ns = (globalThis.BossPlugin ??= {});
  const { SELECTORS, dom } = ns;

  function findJobList() {
    const candidates = dom.queryAll(SELECTORS.jobList, document);
    // 列表根节点的职责只是限定岗位卡片查询范围，它本身不一定可滚动。
    const withCards = candidates.find((element) =>
      dom.queryFirst(SELECTORS.jobCard, element) || dom.queryFirst(SELECTORS.cardLink, element)
    );
    if (withCards) {
      if (ns.CONFIG.debugSelectors) ns.logger.debug("[Selector] jobList => 岗位列表根节点", withCards);
      return withCards;
    }

    if (candidates.length) return candidates[0];

    // class 全部失效时，使用多个岗位卡片/详情链接计算公共祖先作为列表根节点。
    let cards = dom.queryAll(SELECTORS.jobCard, document);
    if (!cards.length) {
      cards = dom.queryAll(SELECTORS.cardLink, document)
        .map((link) => link.closest("li") || link.parentElement)
        .filter(Boolean);
    }
    if (!cards.length) return null;

    let ancestor = cards[0];
    while (ancestor && ancestor !== document.body) {
      if (cards.slice(0, 5).every((card) => ancestor.contains(card))) {
        if (ns.CONFIG.debugSelectors) ns.logger.debug("[Selector] jobList => 卡片公共祖先 fallback", ancestor);
        return ancestor;
      }
      ancestor = ancestor.parentElement;
    }
    return cards[0].parentElement;
  }

  function findScrollContainer(listRoot = findJobList()) {
    if (!listRoot) return null;
    let element = listRoot;
    while (element && element !== document.body && element !== document.documentElement) {
      const canScroll = element.scrollHeight > element.clientHeight + 20;
      if (canScroll) {
        const overflowY = getComputedStyle(element).overflowY;
        if (["auto", "scroll", "overlay"].includes(overflowY)) {
          if (ns.CONFIG.debugSelectors) ns.logger.debug("[Selector] scrollContainer => 独立滚动容器", element);
          return element;
        }
      }
      element = element.parentElement;
    }

    // 新版页面可能没有左侧独立滚动框，而是由整个文档承担滚动。
    const pageScroller = document.scrollingElement || document.documentElement;
    if (ns.CONFIG.debugSelectors) ns.logger.debug("[Selector] scrollContainer => document.scrollingElement", pageScroller);
    return pageScroller;
  }

  function getVisibleJobs(listRoot = findJobList()) {
    if (!listRoot) return [];
    let cards = dom.queryAll(SELECTORS.jobCard, listRoot);
    if (!cards.length) {
      const links = dom.queryAll(SELECTORS.cardLink, listRoot);
      cards = links.map((link) => link.closest("li") || link.parentElement).filter(Boolean);
    }
    return cards.filter((card) => card.isConnected && card.getClientRects().length > 0);
  }

  function readDataId(element) {
    const names = ["jobid", "jobId", "job-id", "lid", "securityId"];
    for (const name of names) {
      const value = element?.dataset?.[name] || element?.getAttribute?.(`data-${name}`);
      if (value) return value;
    }
    return "";
  }

  function extractIdFromUrl(url) {
    if (!url) return "";
    const detailMatch = url.match(/\/job_detail\/([^/?#.]+)/i);
    if (detailMatch) return detailMatch[1];
    try {
      const parsed = new URL(url, location.href);
      return parsed.searchParams.get("jobId") || parsed.searchParams.get("lid") || "";
    } catch (_error) {
      return "";
    }
  }

  function hash(value) {
    let result = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      result ^= value.charCodeAt(index);
      result = Math.imul(result, 16777619);
    }
    return `fallback-${(result >>> 0).toString(16)}`;
  }

  const EXPERIENCE_PATTERN = /经验不限|无经验|在校\/应届|应届生|1年以内|\d+\s*[-–~至]\s*\d+年|\d+年以上|\d+年以内/;
  const EDUCATION_PATTERN = /学历不限|初中|高中|中专|大专|本科|硕士|博士/;
  const SALARY_PATTERN = /\d+(?:\.\d+)?\s*[-–~至]\s*\d+(?:\.\d+)?\s*[Kk]|\d+\s*[Kk]以上/;
  const ACTIVITY_PATTERN_SOURCE = "(?:刚刚活跃|今日活跃|昨日活跃|前天活跃|本周活跃|本月活跃|在线|\\d+\\s*(?:分钟|小时|日|天|周|月)内活跃)";

  function uniqueTexts(elements) {
    return elements.map((element) => visibleText(element).replace(/\s+/g, " ").trim()).filter(Boolean)
      .filter((value, index, all) => all.indexOf(value) === index);
  }

  function isExperience(value) {
    return EXPERIENCE_PATTERN.test(value || "");
  }

  function isEducation(value) {
    return EDUCATION_PATTERN.test(value || "");
  }

  function isSalary(value) {
    return SALARY_PATTERN.test(normalizeSalary(value || ""));
  }

  function normalizeSalary(value) {
    let hadUnknownPrivateUse = false;
    const normalized = [...(value || "")].map((character) => {
      const codePoint = character.codePointAt(0);
      const offset = codePoint - ns.CONFIG.salaryPrivateUseStart;
      if (offset >= 0 && offset < ns.CONFIG.salaryPrivateUseDigits.length) {
        return ns.CONFIG.salaryPrivateUseDigits[offset];
      }
      if (codePoint >= 0xE000 && codePoint <= 0xF8FF) {
        hadUnknownPrivateUse = true;
        return "?";
      }
      return character;
    }).join("").replace(/\s+/g, "").trim();
    if (hadUnknownPrivateUse) ns.logger.warn("SALARY_PRIVATE_USE_CHAR_UNKNOWN", value);
    return normalized;
  }

  function cleanTags(values) {
    const ignored = /^(收藏|举报|分享|不合适|职位描述|微信扫码分享)$/;
    return values.map((value) => value.trim()).filter((value) =>
      value && value.length <= 40 && !ignored.test(value) &&
      !isExperience(value) && !isEducation(value) && !isSalary(value)
    ).filter((value, index, all) => all.indexOf(value) === index);
  }

  function getCardIdentity(card) {
    let link = null;
    for (const selector of SELECTORS.cardLink) {
      try {
        if (card.matches(selector)) {
          link = card;
          break;
        }
      } catch (_error) {
        // selector 的详细错误会由统一 DOM 工具在其他查询时输出。
      }
    }
    link ||= dom.queryFirst(SELECTORS.cardLink, card);
    const href = link?.href || "";
    const jobId = readDataId(card) || readDataId(link) || extractIdFromUrl(href);
    const title = visibleText(dom.queryFirst(SELECTORS.cardTitle, card)).replace(/\s+/g, " ").trim();
    const company = visibleText(dom.queryFirst(SELECTORS.cardCompany, card)).replace(/\s+/g, " ").trim();
    const salary = normalizeSalary(visibleText(dom.queryFirst(SELECTORS.cardSalary, card)));
    const cardLocation = visibleText(dom.queryFirst(SELECTORS.cardLocation, card)).replace(/\s+/g, " ").trim();
    const meta = uniqueTexts(dom.queryAll(SELECTORS.cardMeta, card));
    return {
      jobId: jobId || href || hash(`${title}|${company}`),
      title,
      company,
      salary,
      location: cardLocation,
      experience: meta.find(isExperience) || "",
      education: meta.find(isEducation) || "",
      tags: cleanTags(meta),
      sourceUrl: href || location.href
    };
  }

  function findDetailRoot() {
    const candidates = dom.queryAll(SELECTORS.detailRoot, document);
    if (!candidates.length) return null;
    const descriptionKeywords = ["职位描述", "岗位职责", "工作职责", "任职要求", "职位要求", "岗位要求"];
    let best = candidates[0];
    let bestScore = -1;
    for (const candidate of candidates) {
      const text = dom.normalizedText(candidate);
      const keywordHits = descriptionKeywords.filter((keyword) => text.includes(keyword)).length;
      const hasTitle = Boolean(dom.queryFirst(SELECTORS.jobTitle, candidate));
      const oversizePenalty = Math.max(0, text.length - 12000);
      const score = keywordHits * 10000 + (hasTitle ? 2000 : 0) + Math.min(text.length, 12000) - oversizePenalty;
      if (score > bestScore) {
        best = candidate;
        bestScore = score;
      }
    }
    if (ns.CONFIG.debugSelectors) ns.logger.debug("[Selector] detailRoot => 语义评分最佳候选", best);
    return best;
  }

  function detailSnapshot() {
    const root = findDetailRoot();
    const title = dom.normalizedText(dom.queryFirst(SELECTORS.jobTitle, root || document));
    const description = visibleText(root ? findJobDescriptionElement(root) : null).replace(/\s+/g, " ").trim();
    return `${title}|${description.slice(0, 100)}`;
  }

  async function waitForJobDetailUpdate(beforeSnapshot, expectedTitle, signal) {
    let stableMatches = 0;
    let lastSnapshot = "";
    return dom.waitFor(() => {
      const root = findDetailRoot();
      if (!root) return null;
      const current = detailSnapshot();
      const title = dom.normalizedText(dom.queryFirst(SELECTORS.jobTitle, root));
      const changed = Boolean(current && current !== beforeSnapshot);
      const expectedPrefix = expectedTitle.replace(/[.…]+$/, "").trim();
      const expectedLoaded = Boolean(expectedPrefix && title && (title === expectedTitle || title.includes(expectedPrefix)));

      // 首个卡片可能已被页面选中，此时快照不变；连续两次稳定匹配即可读取。
      stableMatches = expectedLoaded && current === lastSnapshot ? stableMatches + 1 : 0;
      lastSnapshot = current;
      return changed || stableMatches >= 2 ? root : null;
    }, {
      timeoutMs: ns.CONFIG.detailTimeoutMs,
      intervalMs: ns.CONFIG.pollingIntervalMs,
      signal
    });
  }

  function readText(root, selectors, debugName) {
    return visibleText(dom.queryFirst(selectors, root, debugName)).replace(/\s+/g, " ").trim();
  }

  function visibleText(element) {
    return (element?.innerText || element?.textContent || "")
      .replace(/\u00a0/g, " ")
      .replace(/\r\n?/g, "\n")
      .trim();
  }

  function parseRecruiterActivity(text, maximumDays = ns.CONFIG.recruiterActivityMaxDays ?? 3) {
    const match = String(text || "").match(new RegExp(ACTIVITY_PATTERN_SOURCE));
    const activityText = match?.[0]?.replace(/\s+/g, "").trim() || "";
    if (!activityText) return { text: "", withinAllowedRange: null };

    if (["在线", "刚刚活跃", "今日活跃", "昨日活跃", "前天活跃"].includes(activityText)) {
      return { text: activityText, withinAllowedRange: true };
    }

    const relative = activityText.match(/^(\d+)(分钟|小时|日|天|周|月)内活跃$/);
    if (!relative) {
      // “本周/本月活跃”无法保证在最近 maximumDays 天内，按超出范围处理。
      return { text: activityText, withinAllowedRange: false };
    }

    const amount = Number(relative[1]);
    const unit = relative[2];
    const maximumMinutes = maximumDays * 24 * 60;
    const activityMinutes = {
      分钟: amount,
      小时: amount * 60,
      日: amount * 24 * 60,
      天: amount * 24 * 60,
      周: amount * 7 * 24 * 60,
      月: amount * 30 * 24 * 60
    }[unit];
    return { text: activityText, withinAllowedRange: activityMinutes <= maximumMinutes };
  }

  function getRecruiterActivity(root = findDetailRoot()) {
    return parseRecruiterActivity(visibleText(root));
  }

  function parseRecruiterInfo(text) {
    const pattern = new RegExp(
      `(?:^|\\n|\\s)([\\u4e00-\\u9fa5·]{2,8})\\s+${ACTIVITY_PATTERN_SOURCE}\\s+([^·•\\n]{2,40})\\s*[·•]\\s*([^\\n]{2,30}?)(?=\\s+(?:去App|前往App|工作地址|查看更多信息)|$)`
    );
    const match = text.match(pattern);
    return match ? {
      hrName: match[1].trim(),
      company: match[2].trim(),
      hrTitle: match[3].trim()
    } : { hrName: "", company: "", hrTitle: "" };
  }

  function cleanDescriptionText(rawText) {
    let text = rawText
      // textContent fallback 可能包含页面注入的 style 文本；innerText 正常情况下不会包含。
      .replace(/\.[A-Za-z_$][\w$-]*\s*\{[^{}]*\}/g, "")
      .replace(/举报\s*微信扫码分享/g, "")
      .trim();

    const start = text.search(/职位描述|岗位职责|工作职责/);
    if (start >= 0) text = text.slice(start);

    const endPatterns = [
      new RegExp(`\\s(?:[\\u4e00-\\u9fa5]{2,4}|[\\u4e00-\\u9fa5]{1,4}(?:先生|女士))\\s+${ACTIVITY_PATTERN_SOURCE}`),
      /(?:\n|\s)(?:去App与BOSS随时沟通|前往App与BOSS随时沟通|工作地址|查看更多信息)/
    ];
    let end = text.length;
    for (const pattern of endPatterns) {
      const index = text.search(pattern);
      if (index >= 0) end = Math.min(end, index);
    }
    text = text.slice(0, end)
      // 清理由目标页面插入到可见句子中的防复制干扰词。
      .replace(/kanzhun|来自BOSS直聘|BOSS直聘|boss|直聘/gi, "")
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && !/^(举报|微信扫码分享|收藏|不合适|分享)$/.test(line))
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();

    // 部分页面把技能标签直接拼在“职位描述”后；若能识别正文标题，则丢弃这段标签前缀。
    const bodyMarker = text.search(/【岗位职责】|岗位职责\s*[:：]|工作内容\s*[:：]|一、/);
    if (bodyMarker > "职位描述".length && bodyMarker < 600) {
      text = `职位描述\n${text.slice(bodyMarker)}`;
    } else {
      text = text.replace(/^职位描述[.。]?\s*/, "职位描述\n");
    }
    return text;
  }

  function extractLeadingDescriptionTags(description) {
    const lines = (description || "").split("\n").map((line) => line.trim()).filter(Boolean);
    if (!lines.length) return { description: "", tags: [] };

    const bodyMarkers = /^(?:职位描述\s*[:：]?|公司简介\s*[:：]?|岗位职责\s*[:：]?|工作内容\s*[:：]?|任职要求\s*[:：]?|职位要求\s*[:：]?|技能要求\s*[:：]?|核心职责|硬性条件|[一二三四五六七八九十]+、|[-—•]\s*)/;
    const tags = [];
    let bodyStart = 1;
    if (!/^职位描述/.test(lines[0])) bodyStart = 0;

    while (bodyStart < lines.length) {
      const line = lines[bodyStart];
      if (bodyMarkers.test(line) || line.length > 40) break;
      // 标签通常是单个技术名词或短词组；句子和带终止标点的行应视为正文。
      if (/[。；！]/.test(line) || (/[，,]/.test(line) && line.length > 20)) break;
      tags.push(line);
      bodyStart += 1;
    }

    if (!tags.length) return { description, tags: [] };
    const body = lines.slice(bodyStart);
    if (/^职位描述\s*[:：]?$/.test(body[0] || "")) body.shift();
    return {
      description: ["职位描述", ...body].join("\n").trim(),
      tags: cleanTags(tags)
    };
  }

  function findJobDescriptionElement(root = findDetailRoot()) {
    if (!root) return null;

    const direct = dom.queryFirst(SELECTORS.jobDescription, root, "jobDescription");
    if (visibleText(direct).length >= 50) return direct;

    const keywords = ["职位描述", "岗位职责", "工作职责", "任职要求", "职位要求", "岗位要求"];
    const heading = dom.queryAll([
      "h1", "h2", "h3", "h4", "h5", "strong",
      "[class*='title']", "[class*='heading']"
    ], root).find((element) => {
      const text = dom.normalizedText(element);
      return keywords.some((keyword) => text === keyword || text.startsWith(`${keyword}：`) || text.startsWith(`${keyword}:`));
    });

    if (heading) {
      const section = heading.closest("section, article, [class*='job-sec'], [class*='description']");
      const nearby = [section, heading.parentElement, heading.nextElementSibling, heading.parentElement?.parentElement]
        .filter((element) => element && element !== root && root.contains(element));
      const semanticBlock = nearby.find((element) => (element.textContent || "").trim().length >= 80);
      if (semanticBlock) {
        ns.logger.info("通过职位描述标题定位到描述区域");
        return semanticBlock;
      }
    }

    // 最后 fallback：只在右侧详情根节点内，从含职责/要求关键词的文本块中评分。
    // 即使 class 改版，也不会退化成抓取整个页面。
    const candidates = dom.queryAll([
      "section", "article", "div", "p",
      "[class*='job-sec']", "[class*='description']", "[class*='content']"
    ], root).filter((element) => element !== root);

    let best = null;
    let bestScore = -1;
    for (const element of candidates) {
      const text = dom.normalizedText(element);
      if (text.length < 80) continue;
      const keywordHits = keywords.filter((keyword) => text.includes(keyword)).length;
      const semanticClass = /(job|desc|detail|section|content|text)/i.test(String(element.className));
      if (!keywordHits && !semanticClass) continue;
      const oversizePenalty = Math.max(0, text.length - 6000) * 2;
      const score = keywordHits * 10000 + (semanticClass ? 1000 : 0) + Math.min(text.length, 6000) - oversizePenalty;
      if (score > bestScore) {
        best = element;
        bestScore = score;
      }
    }
    if (best) ns.logger.info("通过详情区语义 fallback 定位到职位描述", best);
    return best;
  }

  function extractCurrentJob(cardIdentity = {}) {
    const root = findDetailRoot();
    if (!root) return null;
    const descriptionElement = findJobDescriptionElement(root);
    const rootText = visibleText(root);
    const normalizedRootText = normalizeSalary(rootText);
    const recruiter = parseRecruiterInfo(rootText);
    const meta = uniqueTexts(dom.queryAll(SELECTORS.detailMeta, root));
    const rawTags = uniqueTexts(dom.queryAll(SELECTORS.jobTags, root));
    const salaryFromText = normalizedRootText.match(SALARY_PATTERN)?.[0]?.replace(/\s+/g, "") || "";
    const salaryDirect = normalizeSalary(readText(root, SELECTORS.salary, "salary"));
    const experienceDirect = readText(root, SELECTORS.experience, "experience");
    const educationDirect = readText(root, SELECTORS.education, "education");
    const companyDirect = readText(root, SELECTORS.companyName, "companyName");
    const hrNameDirect = readText(root, SELECTORS.hrName, "hrName");
    const hrTitleDirect = readText(root, SELECTORS.hrTitle, "hrTitle");
    const experience = cardIdentity.experience ||
      (isExperience(experienceDirect) ? experienceDirect : "") || meta.find(isExperience) || "";
    const education = cardIdentity.education ||
      (isEducation(educationDirect) ? educationDirect : "") || meta.find(isEducation) || "";
    const location = cardIdentity.location || readText(root, SELECTORS.location, "location") ||
      meta.find((value) => !isExperience(value) && !isEducation(value) && !isSalary(value) && value.length <= 30) || "";
    const cleanedDescription = cleanDescriptionText(visibleText(descriptionElement));
    const descriptionParts = extractLeadingDescriptionTags(cleanedDescription);
    const tags = cleanTags([
      ...rawTags,
      ...(cardIdentity.tags || []),
      ...descriptionParts.tags
    ]).filter((tag) => tag !== location);

    const job = {
      job_id: cardIdentity.jobId || extractIdFromUrl(location.href),
      job_name: readText(root, SELECTORS.jobTitle, "jobTitle") || cardIdentity.title || "",
      salary: cardIdentity.salary || (isSalary(salaryDirect) ? salaryDirect : "") || salaryFromText,
      location,
      experience,
      education,
      company_name: recruiter.company || cardIdentity.company || (companyDirect.length <= 50 ? companyDirect : ""),
      hr_name: recruiter.hrName || (hrNameDirect.length <= 16 && !hrNameDirect.includes("活跃") ? hrNameDirect : ""),
      hr_title: recruiter.hrTitle || (hrTitleDirect.length <= 30 ? hrTitleDirect : ""),
      job_description: descriptionParts.description,
      job_tags: tags,
      source_url: cardIdentity.sourceUrl || location.href
    };
    // 无法可靠读取地点时不发送该字段，后端也不会再补入空字符串。
    if (!job.location) delete job.location;
    return job;
  }

  ns.jobExtractor = Object.freeze({
    findJobList,
    findScrollContainer,
    getVisibleJobs,
    getCardIdentity,
    findDetailRoot,
    findJobDescriptionElement,
    cleanDescriptionText,
    extractLeadingDescriptionTags,
    normalizeSalary,
    parseRecruiterActivity,
    getRecruiterActivity,
    parseRecruiterInfo,
    detailSnapshot,
    waitForJobDetailUpdate,
    extractCurrentJob
  });
})();
